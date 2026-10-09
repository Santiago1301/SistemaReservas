/**
 * API Gateway de WanderSync. Única puerta de entrada del frontend: /graphql.
 * Antes de llegar a GraphQL, cada petición pasa por CORS, el límite general
 * por IP y la sesión.
 */
import { readFileSync } from 'node:fs';
import { ApolloServer } from '@apollo/server';
import { expressMiddleware } from '@as-integrations/express5';
import cors from 'cors';
import express from 'express';
import { config } from './config.js';
import { resolvers } from './resolvers.js';
import { limiteGlobal, middlewareSesion, redis } from './seguridad.js';
import { crearLoaders } from './supabase.js';

const typeDefs = readFileSync(new URL('./schema.graphql', import.meta.url), 'utf8');

await redis.connect();

// Apollo trae activada la prevención de CSRF: rechaza peticiones "simples" que un
// formulario de otro sitio podría enviar sin que el navegador pida permiso.
const CODIGOS_PROPIOS = new Set(['NO_AUTENTICADO', 'DATOS_INVALIDOS', 'LIMITE_EXCEDIDO', 'SERVICIO_NO_DISPONIBLE']);
const CODIGOS_DE_CONSULTA = new Set(['GRAPHQL_VALIDATION_FAILED', 'GRAPHQL_PARSE_FAILED', 'BAD_USER_INPUT']);

const apollo = new ApolloServer({
  typeDefs,
  resolvers,
  // Nunca se envían trazas internas al cliente: revelan rutas y librerías.
  includeStacktraceInErrorResponses: false,
  formatError: (formateado, original) => {
    const codigo = formateado.extensions?.code;
    if (CODIGOS_PROPIOS.has(codigo) || CODIGOS_DE_CONSULTA.has(codigo)) return formateado;
    // Un fallo inesperado se registra completo en el servidor y sale genérico.
    console.error('Error no controlado:', original);
    return { message: 'Error interno', extensions: { code: 'ERROR_INTERNO' } };
  },
});
await apollo.start();

const app = express();
app.disable('x-powered-by');

app.get('/health', (_req, res) => res.json({ status: 'ok' }));

app.use(
  '/graphql',
  // Solo el frontend puede llamar con credenciales (la cookie de sesión).
  cors({ origin: config.origenFrontend, credentials: true }),
  express.json({ limit: '100kb' }),
  limiteGlobal,
  middlewareSesion(),
  expressMiddleware(apollo, {
    context: async ({ req, res }) => ({
      req,
      res,
      ip: req.ip,
      usuario: req.session.usuario ?? null,
      loaders: crearLoaders(),
    }),
  }),
);

app.use((_req, res) => res.status(404).json({ error: 'Solo existe /graphql' }));

app.listen(config.puerto, () => console.log(`Gateway GraphQL en http://localhost:${config.puerto}/graphql`));
