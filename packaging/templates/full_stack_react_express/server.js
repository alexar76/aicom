/**
 * Minimal Express API shell — extend with your React static build, auth, and Prisma/DB.
 */
const express = require("express");
const app = express();
const port = Number(process.env.PORT) || 3000;

app.use(express.json());

app.get("/health", (_req, res) => {
  res.json({ status: "ok" });
});

app.get("/api/items", (_req, res) => {
  res.json({ items: [], count: 0 });
});

app.listen(port, "0.0.0.0", () => {
  // eslint-disable-next-line no-console
  console.log(`listening on ${port}`);
});
