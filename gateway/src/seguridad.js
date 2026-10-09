/**
 * Seguridad por diseño del gateway: sesiones en Redis, hashing de contraseñas
 * con Argon2id y límites de peticiones por ruta sensible.
 */
import argon2 from 'argon2';
import { RedisStore } from 'connect-redis';
import session from 'express-session';
import { createClient } from 'redis';
import { config } from './config.js';
import { error } from './errores.js';

export const redis = createClient({ url: config.redisUrl });
redis.on('error', (e) => console.error('Redis:', e.message));

// ---------------------------------------------------------------- Sesiones
const UNA_HORA_MS = 60 * 60 * 1000;

export function middlewareSesion() {
  return session({
    store: new RedisStore({ client: redis, prefix: 'sesion:' }),
    name: 'sid',
    secret: config.sessionSecret,
    resave: false,
    // No se crea sesión hasta que alguien inicia sesión: un visitante anónimo no
    // recibe un identificador que un atacante pudiera haberle "plantado".
    saveUninitialized: false,
    cookie: {
      httpOnly: true, // JavaScript del navegador no puede leerla (mitiga robo por XSS)
      sameSite: 'lax', // no viaja en peticiones iniciadas desde otros sitios (mitiga CSRF)
      secure: config.cookieSegura,
      maxAge: UNA_HORA_MS,
    },
  });
}

/**
 * Mitigación de Session Fixation: al autenticar se descarta el identificador de
 * sesión anterior y se emite uno nuevo. Si un atacante conocía el anterior,
 * deja de servirle.
 */
export function abrirSesion(req, usuario) {
  return new Promise((resolver, rechazar) => {
    req.session.regenerate((fallo) => {
      if (fallo) return rechazar(fallo);
      req.session.usuario = { id: usuario.id, email: usuario.email, nombre: usuario.nombre };
      req.session.save((falloGuardar) => (falloGuardar ? rechazar(falloGuardar) : resolver()));
    });
  });
}

export function cerrarSesion(req, res) {
  return new Promise((resolver, rechazar) => {
    req.session.destroy((fallo) => {
      if (fallo) return rechazar(fallo);
      res.clearCookie('sid');
      resolver();
    });
  });
}

// ------------------------------------------------------------- Contraseñas
// Argon2id con 64 MiB de memoria y 3 pasadas (por encima del mínimo de OWASP).
const OPCIONES_ARGON2 = { type: argon2.argon2id, memoryCost: 65536, timeCost: 3, parallelism: 1 };

export const cifrarContrasena = (contrasena) => argon2.hash(contrasena, OPCIONES_ARGON2);

// Hash de relleno: si el correo no existe se verifica contra este, para que la
// respuesta tarde lo mismo y no delate qué correos están registrados.
const hashSenuelo = await cifrarContrasena('contraseña-que-nadie-usa');

export async function verificarContrasena(hashGuardado, contrasena) {
  const coincide = await argon2.verify(hashGuardado ?? hashSenuelo, contrasena);
  return Boolean(hashGuardado) && coincide;
}

// ----------------------------------------------------- Límite de peticiones
/**
 * Ventana fija en Redis: cuenta los intentos de `clave` y rechaza al pasar de
 * `maximo` dentro de `ventanaSegundos`. Vive en Redis para que el límite se
 * comparta aunque haya varias copias del gateway.
 */
export async function limitar(clave, maximo, ventanaSegundos) {
  const llave = `limite:${clave}`;
  const [intentos] = await redis.multi().incr(llave).expire(llave, ventanaSegundos, 'NX').exec();
  if (Number(intentos) > maximo) {
    const espera = Math.max(await redis.ttl(llave), 1);
    throw error('LIMITE_EXCEDIDO', `Demasiados intentos. Vuelve a intentarlo en ${espera} segundos.`);
  }
}

export const reiniciarLimite = (clave) => redis.del(`limite:${clave}`);

/** Tope general por IP sobre todo el gateway, contra ráfagas automatizadas. */
export async function limiteGlobal(req, res, siguiente) {
  try {
    await limitar(`global:${req.ip}`, 120, 60);
    siguiente();
  } catch (fallo) {
    res.status(429).json({ errors: [{ message: fallo.message, extensions: { code: 'LIMITE_EXCEDIDO' } }] });
  }
}
