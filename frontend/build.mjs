import { build, context } from "esbuild";
import { mkdir, readFile, writeFile, rm } from "node:fs/promises";

const serve = process.argv.includes("--serve");
const api = process.env.VITE_API_URL || "";

const options = {
  entryPoints: { main: "src/main.jsx" },
  bundle: true,
  format: "esm",
  outdir: "dist/assets",
  jsx: "automatic",
  minify: !serve,
  sourcemap: serve,
  target: ["es2022"],
  loader: { ".jsx": "jsx" },
  define: {
    "import.meta.env": JSON.stringify({ VITE_API_URL: api }),
    "process.env.NODE_ENV": JSON.stringify(serve ? "development" : "production"),
  },
  nodePaths: process.env.NODE_PATH ? process.env.NODE_PATH.split(":") : [],
  logLevel: "info",
};

async function html() {
  const src = await readFile("index.html", "utf8");
  const out = src
    .replace('<script type="module" src="/src/main.jsx"></script>', '<link rel="stylesheet" href="./assets/main.css" />\n    <script type="module" src="./assets/main.js"></script>');
  await writeFile("dist/index.html", out);
}

await rm("dist", { recursive: true, force: true });
await mkdir("dist", { recursive: true });
await html();

if (serve) {
  const ctx = await context(options);
  await ctx.watch();
  const { port } = await ctx.serve({ servedir: "dist", port: 5173 });
  console.log(`Dev server: http://localhost:${port}`);
} else {
  await build(options);
}
