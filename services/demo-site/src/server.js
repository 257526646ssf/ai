const express = require("express");

const app = express();
app.use(express.urlencoded({ extended: false }));

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.get("/", (_req, res) => {
  res.redirect("/login");
});

app.get("/login", (req, res) => {
  const hasError = req.query.error === "1";

  res.status(200).send(`
    <!doctype html>
    <html>
      <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0" />
        <title>Demo Login</title>
        <style>
          body { font-family: Segoe UI, sans-serif; background: #f6f8fb; margin: 0; }
          .wrap { max-width: 360px; margin: 80px auto; background: #fff; padding: 24px; border-radius: 12px; box-shadow: 0 12px 30px rgba(0,0,0,.08); }
          label { display: block; margin-top: 12px; font-size: 14px; }
          input { width: 100%; margin-top: 6px; padding: 10px; border: 1px solid #d7dbe3; border-radius: 8px; }
          button { margin-top: 16px; width: 100%; padding: 10px; background: #1463ff; color: white; border: none; border-radius: 8px; cursor: pointer; }
          .error { color: #b00020; font-size: 13px; margin-top: 8px; }
        </style>
      </head>
      <body>
        <main class="wrap">
          <h1 id="login-title">Demo Login</h1>
          <form method="post" action="/login">
            <label for="username">Username</label>
            <input id="username" name="username" type="text" autocomplete="off" />
            <label for="password">Password</label>
            <input id="password" name="password" type="password" autocomplete="off" />
            <button id="login-btn" type="submit">Sign In</button>
          </form>
          ${hasError ? '<p id="error-tip" class="error">Invalid credentials</p>' : ""}
        </main>
      </body>
    </html>
  `);
});

app.post("/login", (req, res) => {
  const username = String(req.body.username || "");
  const password = String(req.body.password || "");

  if (username === "demo" && password === "demo123") {
    return res.redirect(`/dashboard?user=${encodeURIComponent(username)}`);
  }

  return res.redirect("/login?error=1");
});

app.get("/dashboard", (req, res) => {
  const user = String(req.query.user || "guest");
  res.status(200).send(`
    <!doctype html>
    <html>
      <head><meta charset="UTF-8" /><title>Dashboard</title></head>
      <body style="font-family: Segoe UI, sans-serif; padding: 24px;">
        <h1 id="welcome">Welcome, ${user}</h1>
        <p id="status">You are now logged in.</p>
      </body>
    </html>
  `);
});

const port = Number(process.env.DEMO_SITE_PORT || 8200);
app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Demo site listening on ${port}`);
});
