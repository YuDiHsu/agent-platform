import { PGlite } from "@electric-sql/pglite";
import { vector } from "@electric-sql/pglite-pgvector";
import { PGLiteSocketServer } from "@electric-sql/pglite-socket";

const port = Number(process.env.PGLITE_PORT);
const db = new PGlite({ extensions: { vector } });
const server = new PGLiteSocketServer({
  db,
  host: "127.0.0.1",
  port,
  maxConnections: 20,
});
await server.start();
console.log(`READY ${port}`);
