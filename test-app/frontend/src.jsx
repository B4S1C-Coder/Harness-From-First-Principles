import React, {useEffect, useState} from "react";
import {createRoot} from "react-dom/client";
import "./style.css";

async function api(path, options) {
  const response = await fetch("/api/posts" + path, options);
  if (!response.ok) {
    throw new Error(`Request failed (HTTP ${response.status}). Reference ${response.headers.get("X-Request-ID")}.`);
  }
  return response.json();
}

function App() {
  const [view, setView] = useState("Latest");
  const [posts, setPosts] = useState([]);
  const [error, setError] = useState("");
  const [feedError, setFeedError] = useState("");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision(value => value + 1);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setFeedError("");
    api(view === "Popular" ? "/popular" : "", {signal: controller.signal})
      .then(setPosts)
      .catch(err => { if (!controller.signal.aborted) setFeedError(err.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [view, revision]);

  async function publish(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setError("");
    setSending(true);
    try {
      await api("", {
        method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify(Object.fromEntries(new FormData(form)))
      });
      form.elements.body.value = "";
      setView("Latest");
      refresh();
    } catch (err) { setError(err.message); }
    finally { setSending(false); }
  }

  async function like(id) {
    setError("");
    try {
      await api(`/${id}/likes`, {method: "POST"});
      refresh();
    } catch (err) { setError(err.message); }
  }

  return <main>
    <header><span aria-hidden="true">✳</span> Commons</header>
    <h1>Community feed</h1>
    <form onSubmit={publish}>
      <label>Display name<input name="author" maxLength="32" required /></label>
      <label>New post<textarea name="body" placeholder="What’s happening?" maxLength="280" required /></label>
      <button disabled={sending}>{sending ? "Publishing…" : "Publish post"}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    <nav aria-label="Feed order">{["Latest", "Popular"].map(label =>
      <button key={label} aria-pressed={view === label} onClick={() => setView(label)}>{label}</button>
    )}</nav>
    {loading ? <p>Loading posts…</p> : feedError ? <p role="alert">{feedError}</p> :
      posts.length === 0 ? <p>No posts yet. Start the conversation above.</p> :
      posts.map(post => <article key={post.id}>
        <div><strong>{post.author}</strong> <time dateTime={post.created_at}>{new Date(post.created_at).toLocaleString()}</time></div>
        <p>{post.body}</p>
        <button onClick={() => like(post.id)} aria-label={`Like post by ${post.author}`}>♡ Like · {post.likes}</button>
      </article>)}
  </main>;
}

createRoot(document.getElementById("root")).render(<App />);
