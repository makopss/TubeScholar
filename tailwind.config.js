/** TubeScholar 정적 Tailwind 빌드 설정 (기존 index.html 의 tailwind.config 와 동일)
 *  CSS 재생성: npm run build:css  → frontend/vendor/tailwind.css
 *  index.html / app.js 에 새 클래스를 추가했다면 반드시 다시 빌드하세요. */
module.exports = {
  content: ["./frontend/index.html", "./frontend/app.js"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f0f7ff",
          100: "#e0effe",
          500: "#0284c7",
          600: "#0369a1",
          700: "#075985",
        },
        surface: {
          dark: "#0f172a",
          card: "#1e293b",
          border: "#334155",
        },
      },
    },
  },
  plugins: [],
};
