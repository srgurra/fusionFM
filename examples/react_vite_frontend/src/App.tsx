import { useEffect, useState } from "react";

type Health = {
  status: string;
  framework: string;
};

type Task = {
  id: number;
  title: string;
};

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);

  useEffect(() => {
    void Promise.all([
      fetch("/api/health", { credentials: "include" }).then((res) => res.json()),
      fetch("/api/tasks", { credentials: "include" }).then((res) => res.json()),
    ]).then(([healthResponse, taskResponse]) => {
      setHealth(healthResponse);
      setTasks(taskResponse.items);
    });
  }, []);

  return (
    <main className="shell">
      <section className="hero">
        <p className="eyebrow">React + TypeScript + fusionframe</p>
        <h1>Modern frontend, batteries-included Python backend.</h1>
        <p className="lede">
          This Vite app talks to a fusionframe API through standard fetch calls.
        </p>
      </section>

      <section className="panel">
        <h2>Backend status</h2>
        <pre>{health ? JSON.stringify(health, null, 2) : "Loading..."}</pre>
      </section>

      <section className="panel">
        <h2>Tasks</h2>
        <ul>
          {tasks.map((task) => (
            <li key={task.id}>{task.title}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}
