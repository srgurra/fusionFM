import { useEffect, useState } from "react";

type Insight = {
  summary: string;
  repo: { name: string; stars: number; language: string; license: string };
  package: { name: string; version: string; summary: string };
  news: Array<{ title: string; url?: string; points: number }>;
  score: number;
};

const requestBody = {
  owner: "encode",
  repo: "starlette",
  package: "fastapi",
  topic: "python web framework",
};

export default function App() {
  const [csrf, setCsrf] = useState("");
  const [insight, setInsight] = useState<Insight | null>(null);
  const [status, setStatus] = useState("Loading");

  useEffect(() => {
    async function runAcceptanceFlow() {
      const login = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: "demo@example.com",
          password: "demo-password",
        }),
      });
      const loginBody = await login.json();
      setCsrf(loginBody.csrf);

      const insightResponse = await fetch("/api/insights", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": loginBody.csrf,
        },
        credentials: "include",
        body: JSON.stringify(requestBody),
      });
      setInsight(await insightResponse.json());
      setStatus("Ready");
    }

    runAcceptanceFlow().catch((error) => setStatus(error.message));
  }, []);

  return (
    <main>
      <p className="eyebrow">React + TypeScript acceptance flow</p>
      <h1>{status}</h1>
      <p>CSRF token received: {csrf ? "yes" : "no"}</p>
      {insight && (
        <section>
          <h2>{insight.summary}</h2>
          <p>
            {insight.repo.name} has {insight.repo.stars.toLocaleString()} stars.
          </p>
          <p>
            {insight.package.name} latest version: {insight.package.version}
          </p>
          <p>Composite score: {insight.score}</p>
          <ul>
            {insight.news.map((item) => (
              <li key={item.title}>{item.title}</li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
