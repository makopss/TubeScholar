"""Local, deterministic topic tags; manual tags and folders remain independent."""
from collections import Counter
import re
import unicodedata

CLASSIFICATION_VERSION = 1
TOPICS = {
    'programming': ('프로그래밍', '개발', '코딩', '파이썬', '유니티', '알고리즘', '소프트웨어',
                    'programming', 'python', 'javascript', 'typescript', 'unity', 'coding', 'software', 'docker', 'react'),
    'ai': ('인공지능', '머신러닝', '딥러닝', '신경망', '강화학습', '생성형',
           'artificial intelligence', 'machine learning', 'deep learning', 'neural network', 'llm', 'gpt', 'ai'),
    'math': ('수학', '선형대수', '미적분', '벡터', '행렬', '고유값', '기하', '확률', '통계',
             'mathematics', 'math', 'calculus', 'algebra', 'vector', 'matrix', 'eigenvalue', 'geometry', 'statistics'),
    'science': ('과학', '물리', '화학', '생물', '천문', '양자', '상대성', '우주',
                'science', 'physics', 'chemistry', 'biology', 'astronomy', 'quantum', 'relativity'),
    'economics': ('경제', '금융', '회계', '투자', '주식', '경영', '마케팅',
                  'economics', 'finance', 'accounting', 'investment', 'business', 'marketing'),
    'history': ('역사', '세계사', '한국사', '문명', '고고학', 'history', 'civilization', 'archaeology'),
    'language': ('영어', '일본어', '중국어', '한국어', '문법', '발음', '회화', '어학',
                 'english', 'japanese', 'grammar', 'pronunciation', 'vocabulary', 'language learning'),
    'arts': ('예술', '미술', '음악', '영화', '사진', '디자인', '작곡', '연주',
             'art', 'music', 'cinema', 'film', 'photography', 'design', 'painting'),
    'health': ('건강', '의학', '운동', '영양', '수면', '심리', '명상',
               'health', 'medicine', 'fitness', 'nutrition', 'sleep', 'psychology', 'meditation'),
    'society': ('사회', '철학', '정치', '윤리', '인문', '교육',
                'society', 'philosophy', 'politics', 'ethics', 'humanities', 'education'),
}
_STOP = set('the and for with from this that into your what how why intro introduction chapter lesson study note notes video learning '
            '강의 학습 노트 영상 개요 요약 정리 소개 핵심 이해 설명 주요 내용 배경 지식 용어 퀴즈 문제 결론'.split())


def _normal(text):
    return unicodedata.normalize('NFKC', str(text or '')).casefold()


def _hits(text, term):
    if term.isascii():
        return len(re.findall(r'(?<![a-z0-9])' + re.escape(term) + r'(?![a-z0-9])', text))
    return text.count(term)


def classify_note(title, markdown):
    """Score title/headings above prose; uncertain notes stay in Other."""
    title = _normal(title)[:1000]
    body = re.sub(r'```[\s\S]*?```', '', str(markdown or '')[:60000])
    headings = '\n'.join(re.findall(r'^#{1,6}\s+(.+)$', body, flags=re.MULTILINE))
    normalized_body, normalized_headings = _normal(body), _normal(headings)
    scores = {}
    for topic, terms in TOPICS.items():
        score = sum(6 * min(_hits(title, term), 2) +
                    3 * min(_hits(normalized_headings, term), 2) +
                    min(_hits(normalized_body, term), 3) for term in terms)
        if score >= 3:
            scores[topic] = score
    strongest = max(scores.values(), default=0)
    topics = [topic for topic in sorted(scores, key=lambda topic: (-scores[topic], topic))
              if scores[topic] >= max(3, strongest * .4)][:3]
    words = re.findall(r'[^\W\d_][\w+#-]{1,34}', title + '\n' + normalized_headings)
    counts = Counter(word for word in words if word not in _STOP and not re.fullmatch(r'\d+강', word))
    keywords = [word for word, _ in counts.most_common(5)]
    return {'auto_tags': topics, 'auto_keywords': keywords,
            'classification_version': CLASSIFICATION_VERSION}
