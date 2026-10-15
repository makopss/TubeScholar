"""Offline regression tests. Run: .venv/Scripts/python.exe -B scripts/test_analysis.py"""
import asyncio
import contextlib
import io
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch
import uuid
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
_test_data = tempfile.TemporaryDirectory(prefix="tubescholar-tests-")
os.environ["TUBESCHOLAR_DATA_DIR"] = _test_data.name

import httpx
import analysis_jobs as jobs
import analyzer
import app as api
import media_process
import storage
import stt
jobs.log.disabled = True

SRT = "1\n00:00:00,000 --> 00:00:02,000\nHello world.\n"


@contextlib.contextmanager
def bound_job(**kwargs):
    job = jobs.begin_job(**kwargs)
    token = jobs._context.set(job)
    try:
        yield job
    finally:
        jobs._context.reset(token)


class JobTests(unittest.TestCase):
    def test_cancel_is_not_reset_by_a_new_job(self):
        with bound_job() as first:
            jobs.request_analysis_cancel(first.job_id)
            second = jobs.begin_job()
            with self.assertRaises(jobs.AnalysisStopped):
                jobs.reset_analysis_cancel()
            jobs.update_analysis_state("completed", event="completed")
            self.assertEqual(jobs.get_analysis_state(first.job_id)["status"], "cancelled")
            self.assertEqual(jobs.get_analysis_state(second.job_id)["status"], "processing")

    def test_late_cancel_only_targets_its_own_job(self):
        old = jobs.begin_job()
        new = jobs.begin_job()
        jobs.request_analysis_cancel(old.job_id)
        self.assertFalse(new.cancel.is_set())

    def test_cancel_can_arrive_before_the_upload(self):
        job_id = uuid.uuid4().hex
        jobs.request_analysis_cancel(job_id)
        with bound_job(job_id=job_id):
            with self.assertRaises(jobs.AnalysisStopped):
                jobs.check_analysis()

    def test_deadline_prevents_writes(self):
        with bound_job(timeout=0):
            with self.assertRaises(jobs.AnalysisStopped) as stopped:
                with jobs.analysis_commit():
                    self.fail("expired job committed")
            self.assertEqual(stopped.exception.status_code, 504)

    def test_model_response_does_not_complete_the_job(self):
        with bound_job() as job:
            jobs.update_analysis_state("completed", event="completed")
            self.assertEqual(jobs.get_analysis_state(job.job_id)["status"], "processing")

    def test_ffmpeg_is_killed_on_cancel(self):
        with bound_job() as job:
            # A local child stands in for a stalled FFmpeg, without touching a video.
            timer = threading.Timer(0.15, lambda: jobs.request_analysis_cancel(job.job_id))
            timer.start()
            try:
                started = time.monotonic()
                with self.assertRaises(jobs.AnalysisStopped):
                    media_process.run_ffmpeg([sys.executable, "-c", "import time; time.sleep(30)"], timeout=2)
                self.assertLess(time.monotonic() - started, 3)
            finally:
                timer.cancel()
                timer.join()

    def test_ffmpeg_timeout(self):
        with bound_job():
            with self.assertRaises(TimeoutError):
                media_process.run_ffmpeg([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.15)


class AsyncOperationTests(unittest.IsolatedAsyncioTestCase):
    async def test_timeout_cancels_the_actual_operation(self):
        stopped = asyncio.Event()

        async def stalled():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        with bound_job():
            with self.assertRaises(TimeoutError):
                await jobs.await_operation(stalled, 0.03)
        self.assertTrue(stopped.is_set())

    async def test_cancel_closes_the_actual_operation(self):
        stopped = asyncio.Event()

        async def stalled():
            try:
                await asyncio.Event().wait()
            finally:
                stopped.set()

        with bound_job() as job:
            asyncio.get_running_loop().call_later(0.02, jobs.request_analysis_cancel, job.job_id)
            with self.assertRaises(jobs.AnalysisStopped):
                await jobs.await_operation(stalled, 1)
        self.assertTrue(stopped.is_set())


class AnalyzerTests(unittest.TestCase):
    def test_model_fallback_respects_the_total_deadline(self):
        calls = []
        with bound_job() as job:
            def timeout(*args, **kwargs):
                calls.append(kwargs["model"])
                job.started -= job.timeout + 1
                raise TimeoutError("timeout")
            with patch.object(analyzer, "_call_generate_content_interruptible", side_effect=timeout):
                with self.assertRaises(jobs.AnalysisStopped) as stopped:
                    analyzer._generate_with_model_fallback("fake", "text", "system", ["first", "second"])
            self.assertEqual(stopped.exception.status_code, 504)
        self.assertEqual(calls, ["first"])

    def test_groq_timeout_closes_client_and_file(self):
        closed = []
        opened_files = []

        class Client:
            def __init__(self, **kwargs):
                self.audio = types.SimpleNamespace(transcriptions=self)

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                closed.append(True)

            async def create(self, **kwargs):
                opened_files.append(kwargs["file"][1])
                await asyncio.Event().wait()

        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / "test.mp3"
            audio.write_bytes(b"fake audio")
            def run(factory, timeout):
                return asyncio.run(jobs.await_operation(factory, 0.02))
            with bound_job(), patch.object(stt, "AsyncGroq", Client), patch.object(stt, "run_async_operation", side_effect=run):
                result = stt.transcribe_audio_groq(str(audio), api_key="fake")
        self.assertFalse(result["success"])
        self.assertEqual(closed, [True])
        self.assertTrue(opened_files[0].closed)

    def test_gemini_clients_close_after_timeout(self):
        closed = []

        class Client:
            def __init__(self, **kwargs):
                self.aio = self
                self.models = self

            async def generate_content(self, **kwargs):
                await asyncio.Event().wait()

            async def aclose(self):
                closed.append("async")

            def close(self):
                closed.append("sync")

        with bound_job(), patch.object(analyzer.genai, "Client", Client):
            with self.assertRaises(TimeoutError):
                analyzer._call_generate_content_interruptible("fake", "fake", "text", analyzer.types.GenerateContentConfig(), 0.03)
        self.assertEqual(closed, ["async", "sync"])

    def audio_result(self, text, cleanup_fails=False):
        def io_call(key, operation, timeout, **kwargs):
            if kwargs.get("check_job") is False:
                if cleanup_fails:
                    raise TimeoutError("cleanup")
                return None
            return types.SimpleNamespace(name="fake-upload")

        with bound_job(), patch.object(analyzer, "_gemini_io", side_effect=io_call), patch.object(
            analyzer, "_generate_with_model_fallback", return_value={"success": True, "text": text, "model_used": "fake"}
        ):
            return analyzer.generate_study_note_from_audio("fake.mp3", api_key="fake")

    def test_note_summary_is_never_a_subtitle(self):
        result = self.audio_result("===STUDY_NOTE===\n[00:10] Summary, not spoken dialogue.")
        self.assertTrue(result["success"])
        self.assertEqual(result["subtitles"], [])
        self.assertEqual(result["subtitle_status"], "unavailable")
        self.assertTrue(result["warning"])

    def test_invalid_srt_is_not_treated_as_a_subtitle(self):
        result = self.audio_result("===STUDY_NOTE===\nA note\n===SUBTITLES_SRT===\nnot SRT")
        self.assertEqual(result["subtitles"], [])

    def test_valid_srt_and_note_survive_cleanup_failure(self):
        result = self.audio_result("===STUDY_NOTE===\nA note\n===SUBTITLES_SRT===\n" + SRT, cleanup_fails=True)
        self.assertTrue(result["success"])
        self.assertEqual(result["subtitle_status"], "complete")
        self.assertEqual(result["subtitles"][0]["text"], "Hello world.")

    def test_fenced_srt_is_accepted(self):
        result = self.audio_result("===STUDY_NOTE===\nA note\n===SUBTITLES_SRT===\n```srt\n" + SRT + "```\n")
        self.assertEqual(result["subtitle_status"], "complete")


class APITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app), base_url="http://localhost",
                                        headers={"x-tubescholar": "1"})

    async def asyncTearDown(self):
        await self.client.aclose()

    async def test_supplied_subtitles_skip_audio_and_retain_video_on_note_failure(self):
        job_id = uuid.uuid4().hex
        with patch.object(api, "run_ffmpeg") as ffmpeg, patch.object(api, "transcribe_audio_groq") as groq, patch.object(
            api, "generate_study_note_gemini", return_value={"success": False, "error": "timeout"}
        ):
            response = await self.client.post("/api/local/video-analyze", headers={"x-analysis-id": job_id},
                data={"subtitle_text": SRT}, files={"video": ("lesson.mp4", b"original-video")})
        self.assertEqual(response.status_code, 500)
        ffmpeg.assert_not_called()
        groq.assert_not_called()
        note_id = jobs.get_analysis_state(job_id)["checkpoint_note_id"]
        note = (await self.client.get(f"/api/notes/{note_id}")).json()
        self.assertTrue(note["metadata"]["local_video_available"])
        media = await self.client.get(f"/api/notes/{note_id}/video", headers={"Range": "bytes=0-7"})
        self.assertEqual(media.status_code, 206)
        self.assertEqual(media.content, b"original")
        self.assertEqual(media.headers["content-range"], "bytes 0-7/14")

    async def test_reconnect_deduplicates_preserves_edits_and_deletes_only_last_reference(self):
        info = {"video_id": "local_" + uuid.uuid4().hex, "video_type": "local", "title": "Old note"}
        first = storage.save_note(info, "original", subtitles=[])['note_id']
        self.assertFalse((await self.client.get(f"/api/notes/{first}")).json()["metadata"]["local_video_available"])
        response = await self.client.post(f"/api/notes/{first}/video", files={"video": ("lesson.mp4", b"shared-video")})
        self.assertEqual(response.status_code, 200, response.text)
        path = storage.local_video_path(response.json()["local_video"])
        second = storage.save_note(info, "second version")['note_id']
        self.assertEqual(storage.get_note(second)["metadata"]["local_video"]["filename"], Path(path).name)
        storage.save_note(info, "updated", note_id=first)
        self.assertEqual((await self.client.get(f"/api/notes/{first}/video")).content, b"shared-video")
        same = await self.client.post(f"/api/notes/{second}/video", files={"video": ("renamed.mp4", b"shared-video")})
        self.assertEqual(same.json()["local_video"]["filename"], Path(path).name)
        replaced = await self.client.post(f"/api/notes/{first}/video", files={"video": ("replacement.mp4", b"other-video")})
        replacement = storage.local_video_path(replaced.json()["local_video"])
        self.assertTrue(Path(path).exists())
        storage.delete_note(first)
        self.assertFalse(Path(replacement).exists())
        self.assertTrue(Path(path).exists())
        storage.delete_note(second)
        self.assertFalse(Path(path).exists())

    async def test_video_reconnect_rejects_youtube_empty_and_oversize_files(self):
        youtube = storage.save_note({"video_id": "youtube-test", "title": "YT"}, "note")["note_id"]
        response = await self.client.post(f"/api/notes/{youtube}/video", files={"video": ("v.mp4", b"data")})
        self.assertEqual(response.status_code, 400)
        local = storage.save_note({"video_id": "local_" + uuid.uuid4().hex, "video_type": "local"}, "note")["note_id"]
        response = await self.client.post(f"/api/notes/{local}/video", files={"video": ("page.html", b"<script>bad()</script>")})
        self.assertEqual(response.status_code, 400)
        response = await self.client.post(f"/api/notes/{local}/video", files={"video": ("v.mp4", b"")})
        self.assertEqual(response.status_code, 400)
        with patch.object(jobs, "MAX_LOCAL_VIDEO_BYTES", 8):
            response = await self.client.post(f"/api/notes/{local}/video", files={"video": ("v.mp4", b"0" * 70000)})
        self.assertEqual(response.status_code, 413)
        with patch.object(storage, "MAX_LOCAL_VIDEO_BYTES", 2):
            response = await self.client.post(f"/api/notes/{local}/video", files={"video": ("v.mp4", b"too large")})
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("local_video", storage.get_note(local)["metadata"])

    async def test_video_references_cannot_escape_managed_directory(self):
        self.assertIsNone(storage.local_video_path({"filename": "../../.env"}))
        self.assertIsNone(storage.local_video_path({"filename": str(Path(_test_data.name) / "secret.mp4")}))
        self.assertEqual((await self.client.get("/api/notes/unknown/video")).status_code, 404)

    async def test_cancelling_video_retention_does_not_publish_a_partial_file(self):
        note_id = storage.save_note({"video_id": "local_" + uuid.uuid4().hex, "video_type": "local"}, "note")["note_id"]
        with bound_job() as job:
            class CancelledStream(io.BytesIO):
                def read(self, size):
                    data = super().read(size)
                    job.cancel.set()
                    return data
            with self.assertRaises(jobs.AnalysisStopped):
                storage.attach_note_video(note_id, CancelledStream(b"partial"), "v.mp4", jobs.check_analysis, jobs.analysis_commit)
        self.assertNotIn("local_video", storage.get_note(note_id)["metadata"])
        self.assertEqual(list(Path(storage.VIDEOS_DIR).glob("*.upload")), [])

    async def test_gemini_audio_without_groq_also_retains_video_without_fake_subtitles(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}), patch.object(api, "run_ffmpeg"), patch.object(
            api, "generate_study_note_from_audio", return_value={"success": True, "markdown": "note", "model_used": "fake", "subtitles": [], "subtitle_status": "unavailable"}
        ):
            response = await self.client.post("/api/local/video-analyze", files={"video": ("v.mp4", b"audio-video")})
        self.assertEqual(response.status_code, 200, response.text)
        data = response.json()
        self.assertEqual(data["subtitles"], [])
        self.assertEqual((await self.client.get(f"/api/notes/{data['note_id']}/video")).content, b"audio-video")

    async def test_prompt_copy_needs_subtitles_but_never_calls_generation(self):
        with patch.object(api, "generate_study_note_gemini") as generate:
            valid = await self.client.post("/api/local/prompt", json={"title": "test", "subtitle_text": SRT})
            invalid = await self.client.post("/api/local/prompt", json={"title": "test", "subtitle_text": ""})
        self.assertEqual(valid.status_code, 200)
        self.assertTrue(valid.json()["prompt"])
        self.assertIn("Hello world.", valid.json()["prompt"])
        self.assertEqual(invalid.status_code, 400)
        generate.assert_not_called()

    async def post(self, path="/api/local/analyze", title="test", job_id=None):
        job_id = job_id or uuid.uuid4().hex
        response = await self.client.post(path, headers={"x-analysis-id": job_id}, json={"title": title, "subtitle_text": SRT})
        return job_id, response

    async def test_validation_error_finishes_the_state(self):
        job_id, response = await self.post("/api/analyze")
        self.assertEqual(response.status_code, 422)
        self.assertEqual(jobs.get_analysis_state(job_id)["status"], "error")

    async def test_non_subtitle_text_is_rejected_before_generation(self):
        with patch.object(api, "generate_study_note_gemini") as generate:
            response = await self.client.post("/api/local/analyze", json={"title": "bad", "subtitle_text": "not SRT"})
        self.assertEqual(response.status_code, 400)
        generate.assert_not_called()

    async def test_missing_api_key_preserves_transcript(self):
        with patch.object(api, "generate_study_note_gemini", return_value={"success": False, "error": "missing key"}):
            job_id, response = await self.post()
        self.assertEqual(response.status_code, 500)
        state = jobs.get_analysis_state(job_id)
        self.assertEqual(state["status"], "error")
        note = storage.get_note(state["checkpoint_note_id"])
        self.assertEqual(note["metadata"]["subtitles"][0]["text"], "Hello world.")

    async def test_stale_request_cannot_save_after_new_request(self):
        entered = threading.Event()

        def generate(video_info, transcript_data=None, **kwargs):
            if video_info["title"] == "old":
                entered.set()
                while True:
                    jobs.check_analysis()
                    time.sleep(0.01)
            return {"success": True, "markdown": "new note", "model_used": "fake"}

        with patch.object(api, "generate_study_note_gemini", side_effect=generate):
            old_id = uuid.uuid4().hex
            old = asyncio.create_task(self.post(title="old", job_id=old_id))
            for _ in range(200):
                if entered.is_set():
                    break
                await asyncio.sleep(0.01)
            self.assertTrue(entered.is_set())
            new_id, new = await self.post(title="new")
            _, old_response = await asyncio.wait_for(old, 3)
        self.assertEqual(old_response.status_code, 499)
        self.assertEqual(new.status_code, 200)
        self.assertEqual(jobs.get_analysis_state(new_id)["status"], "completed")
        old_state = jobs.get_analysis_state(old_id)
        self.assertEqual(old_state["status"], "cancelled")
        self.assertNotEqual(storage.get_note(old_state["checkpoint_note_id"])["markdown"], "new note")

    async def test_completed_only_after_save(self):
        real_save = api._save_note
        observed = []

        def save(*args, **kwargs):
            observed.append(jobs.get_analysis_state(jobs.current_job().job_id)["status"])
            return real_save(*args, **kwargs)

        with patch.object(api, "_save_note", side_effect=save), patch.object(api, "generate_study_note_gemini", return_value={"success": True, "markdown": "saved", "model_used": "fake"}):
            job_id, response = await self.post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(observed, ["processing", "processing"])
        self.assertEqual(jobs.get_analysis_state(job_id)["status"], "completed")

    async def test_disk_failure_is_an_error(self):
        with patch.object(api, "_save_note", side_effect=OSError("disk full")):
            job_id, response = await self.post()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(jobs.get_analysis_state(job_id)["status"], "error")

    async def test_declared_oversize_upload_rejected_before_handler(self):
        with patch.object(jobs, "MAX_LOCAL_VIDEO_BYTES", 8), patch.object(api, "run_ffmpeg") as ffmpeg:
            job_id = uuid.uuid4().hex
            response = await self.client.post("/api/local/video-analyze", headers={"x-analysis-id": job_id},
                                              files={"video": ("test.mp4", b"0" * 70000)})
        self.assertEqual(response.status_code, 413)
        ffmpeg.assert_not_called()
        self.assertEqual(jobs.get_analysis_state(job_id)["status"], "error")

    async def test_chunked_oversize_upload_rejected_while_receiving(self):
        async def chunks():
            yield b'--test\r\nContent-Disposition: form-data; name="video"; filename="test.mp4"\r\nContent-Type: video/mp4\r\n\r\n'
            for _ in range(7):
                yield b"0" * 10000
            yield b"\r\n--test--\r\n"

        with patch.object(jobs, "MAX_LOCAL_VIDEO_BYTES", 8), patch.object(api, "run_ffmpeg") as ffmpeg:
            response = await self.client.post("/api/local/video-analyze", headers={"x-analysis-id": uuid.uuid4().hex,
                "content-type": "multipart/form-data; boundary=test"}, content=chunks())
        self.assertEqual(response.status_code, 413)
        ffmpeg.assert_not_called()

    async def test_local_stt_survives_note_failure(self):
        subtitles = [{"start": 0, "end": 2, "duration": 2, "timestamp": "00:00", "text": "Actual speech"}]
        with patch.dict(os.environ, {"GROQ_API_KEY": "fake"}), patch.object(api, "run_ffmpeg"), patch.object(
            api, "transcribe_audio_groq", return_value={"success": True, "subtitles": subtitles}
        ), patch.object(api, "generate_study_note_gemini", return_value={"success": False, "error": "model timeout"}):
            job_id = uuid.uuid4().hex
            response = await self.client.post("/api/local/video-analyze", headers={"x-analysis-id": job_id},
                                              files={"video": ("test.mp4", b"fake-video")})
        self.assertEqual(response.status_code, 500)
        state = jobs.get_analysis_state(job_id)
        note = storage.get_note(state["checkpoint_note_id"])
        self.assertEqual(note["metadata"]["subtitles"][0]["text"], "Actual speech")

    async def test_real_ffmpeg_and_successful_local_pipeline(self):
        audio = io.BytesIO()
        with wave.open(audio, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b"\0\0" * 16000)

        def transcribe(path, **kwargs):
            self.assertGreater(Path(path).stat().st_size, 100)
            return {"success": True, "subtitles": [{"start": 0, "end": 1, "timestamp": "00:00", "text": "Test speech"}]}

        with patch.dict(os.environ, {"GROQ_API_KEY": "fake"}), patch.object(api, "transcribe_audio_groq", side_effect=transcribe), patch.object(
            api, "generate_study_note_gemini", return_value={"success": True, "markdown": "Final note", "model_used": "fake"}
        ):
            job_id = uuid.uuid4().hex
            response = await self.client.post("/api/local/video-analyze", headers={"x-analysis-id": job_id},
                                              files={"video": ("test.wav", audio.getvalue())})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result["markdown"], "Final note")
        self.assertEqual(result["note_id"], jobs.get_analysis_state(job_id)["checkpoint_note_id"])
        self.assertEqual(storage.get_note(result["note_id"])["metadata"]["subtitle_status"], "complete")

    async def test_upload_deadline_is_enforced_during_receive(self):
        async def chunks():
            yield b'--test\r\nContent-Disposition: form-data; name="video"; filename="test.mp4"\r\n\r\n'
            await asyncio.Event().wait()

        with patch.object(jobs, "ANALYSIS_TIMEOUT_SECONDS", 0.03):
            response = await asyncio.wait_for(self.client.post("/api/local/video-analyze", headers={
                "x-analysis-id": uuid.uuid4().hex, "content-type": "multipart/form-data; boundary=test",
            }, content=chunks()), 2)
        self.assertEqual(response.status_code, 504)

    async def test_cancel_upload_before_handler(self):
        started = asyncio.Event()
        job_id = uuid.uuid4().hex

        async def chunks():
            yield b'--test\r\nContent-Disposition: form-data; name="video"; filename="test.mp4"\r\n\r\n'
            started.set()
            await asyncio.Event().wait()

        with patch.object(api, "run_ffmpeg") as ffmpeg:
            upload = asyncio.create_task(self.client.post("/api/local/video-analyze", headers={
                "x-analysis-id": job_id, "content-type": "multipart/form-data; boundary=test",
            }, content=chunks()))
            await asyncio.wait_for(started.wait(), 2)
            await self.client.post("/api/analysis/cancel", params={"job_id": job_id})
            response = await asyncio.wait_for(upload, 2)
        self.assertEqual(response.status_code, 499)
        ffmpeg.assert_not_called()


if __name__ == "__main__":
    try:
        unittest.main()
    finally:
        _test_data.cleanup()
