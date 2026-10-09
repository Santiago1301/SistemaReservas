import { GraphQLScalarType, Kind } from 'graphql';
import { config, DESTINOS } from './config.js';
import { error } from './errores.js';
import { crearOrden, listarOrdenes, obtenerOrden } from './ordenes.js';
import {
  abrirSesion,
  cerrarSesion,
  cifrarContrasena,
  limitar,
  reiniciarLimite,
  verificarContrasena,
} from './seguridad.js';
import { buscarUsuario, crearUsuario, listar, masBaratos } from './supabase.js';

// ------------------------------------------------------------------ Scalars
const FORMATO_FECHA = /^\d{4}-\d{2}-\d{2}$/;

function leerFecha(valor) {
  if (typeof valor !== 'string' || !FORMATO_FECHA.test(valor) || Number.isNaN(Date.parse(valor))) {
    throw error('DATOS_INVALIDOS', `Fecha inválida: ${valor}. Formato esperado: AAAA-MM-DD`);
  }
  return valor;
}

const DateScalar = new GraphQLScalarType({
  name: 'Date',
  serialize: (valor) => String(valor).slice(0, 10),
  parseValue: leerFecha,
  parseLiteral: (nodo) => leerFecha(nodo.kind === Kind.STRING ? nodo.value : null),
});

const DateTimeScalar = new GraphQLScalarType({
  name: 'DateTime',
  serialize: (valor) => new Date(valor).toISOString(),
});

// ----------------------------------------------------------------- Utilidades
/**
 * Campos que el cliente pidió bajo el campo actual (o bajo uno de sus hijos,
 * siguiendo `ruta`). Con esto el gateway le pide a Supabase solo esas columnas.
 */
function camposPedidos(info, ruta = []) {
  const recolectar = (selecciones, pendiente) => {
    const campos = new Set();
    for (const seleccion of selecciones ?? []) {
      if (seleccion.kind === Kind.FIELD) {
        const nombre = seleccion.name.value;
        if (pendiente.length === 0) {
          if (!nombre.startsWith('__')) campos.add(nombre);
        } else if (nombre === pendiente[0]) {
          recolectar(seleccion.selectionSet?.selections, pendiente.slice(1)).forEach((c) => campos.add(c));
        }
      } else {
        const interno =
          seleccion.kind === Kind.FRAGMENT_SPREAD
            ? info.fragments[seleccion.name.value].selectionSet
            : seleccion.selectionSet;
        recolectar(interno.selections, pendiente).forEach((c) => campos.add(c));
      }
    }
    return campos;
  };
  return info.fieldNodes.flatMap((nodo) => [...recolectar(nodo.selectionSet?.selections, ruta)]);
}

const noches = (viaje) => Math.round((Date.parse(viaje.fechaFin) - Date.parse(viaje.fechaInicio)) / 86_400_000);

function exigirSesion(contexto) {
  if (!contexto.usuario) throw error('NO_AUTENTICADO', 'Debes iniciar sesión');
  return contexto.usuario;
}

const FORMATO_EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ------------------------------------------------------------------ Resolvers
export const resolvers = {
  Date: DateScalar,
  DateTime: DateTimeScalar,

  Query: {
    destinos: () => Object.keys(DESTINOS),

    // No consulta nada todavía: cada lista se resuelve solo si el cliente la pide.
    disponibilidad: (_, viaje) => {
      if (!DESTINOS[viaje.destino]) throw error('DATOS_INVALIDOS', `Destino no disponible: ${viaje.destino}`);
      if (viaje.fechaFin <= viaje.fechaInicio) {
        throw error('DATOS_INVALIDOS', 'La fecha de fin debe ser posterior a la de inicio');
      }
      if (viaje.pasajeros < 1 || viaje.pasajeros > 9) throw error('DATOS_INVALIDOS', 'Pasajeros: entre 1 y 9');
      return viaje;
    },

    me: (_, __, contexto) => contexto.usuario,

    orden: async (_, { id }, contexto) => {
      const usuario = exigirSesion(contexto);
      const orden = await obtenerOrden(id);
      // Una orden ajena se responde igual que una inexistente, para no confirmar que existe.
      return orden && orden.usuarioId === usuario.id ? orden : null;
    },

    misOrdenes: (_, __, contexto) => listarOrdenes(exigirSesion(contexto).id),
  },

  Disponibilidad: {
    vuelos: (viaje, { limite }, _, info) => listar('vuelos', viaje, camposPedidos(info), limite),
    hoteles: (viaje, { limite }, _, info) => listar('hoteles', viaje, camposPedidos(info), limite),
    autos: (viaje, { limite }, _, info) => listar('autos', viaje, camposPedidos(info), limite),

    paqueteMasEconomico: async (viaje, _, __, info) => {
      const paquete = await masBaratos(viaje, {
        vuelos: camposPedidos(info, ['vuelo']),
        hoteles: camposPedidos(info, ['hotel']),
        autos: camposPedidos(info, ['auto']),
      });
      if (!paquete) return null;
      const n = noches(viaje);
      const totalCop =
        paquete.vuelo.precioCop * viaje.pasajeros + (paquete.hotel.precioNocheCop + paquete.auto.precioDiaCop) * n;
      return { ...paquete, noches: n, totalCop };
    },
  },

  Orden: {
    vuelo: (orden, _, { loaders }) => loaders.vuelo.load(orden.vueloId),
    hotel: (orden, _, { loaders }) => loaders.hotel.load(orden.hotelId),
    auto: (orden, _, { loaders }) => loaders.auto.load(orden.autoId),
    estadoPago: async (orden) => (orden.pasos ? orden : await obtenerOrden(orden.id)).pago?.estado ?? null,
    pasos: async (orden) => orden.pasos ?? (await obtenerOrden(orden.id)).pasos,
    urlPrefect: (orden) => (orden.flowRunId ? `${config.prefectUiUrl}/runs/flow-run/${orden.flowRunId}` : null),
  },

  Mutation: {
    registrar: async (_, { email, nombre, contrasena }, contexto) => {
      await limitar(`registro:${contexto.ip}`, 5, 600);

      const correo = email.trim().toLowerCase();
      if (!FORMATO_EMAIL.test(correo) || correo.length > 254) throw error('DATOS_INVALIDOS', 'Correo inválido');
      if (nombre.trim().length < 2 || nombre.length > 80) throw error('DATOS_INVALIDOS', 'Nombre inválido');
      if (contrasena.length < 10 || contrasena.length > 128) {
        throw error('DATOS_INVALIDOS', 'La contraseña debe tener entre 10 y 128 caracteres');
      }
      if (await buscarUsuario(correo)) throw error('DATOS_INVALIDOS', 'Ya existe una cuenta con ese correo');

      const usuario = await crearUsuario({
        email: correo,
        nombre: nombre.trim(),
        hashContrasena: await cifrarContrasena(contrasena),
      });
      await abrirSesion(contexto.req, usuario);
      return usuario;
    },

    iniciarSesion: async (_, { email, contrasena }, contexto) => {
      const correo = email.trim().toLowerCase();
      // Dos topes: uno por IP (muchos correos desde un sitio) y otro por IP+correo
      // (fuerza bruta contra una cuenta).
      await limitar(`login:${contexto.ip}`, 20, 300);
      await limitar(`login:${contexto.ip}:${correo}`, 5, 300);

      const usuario = await buscarUsuario(correo);
      const valida = await verificarContrasena(usuario?.hashContrasena, contrasena);
      // Mismo mensaje si falla el correo o la contraseña: no revela cuál de los dos.
      if (!valida) throw error('NO_AUTENTICADO', 'Correo o contraseña incorrectos');

      await reiniciarLimite(`login:${contexto.ip}:${correo}`); // los aciertos no cuentan como intentos
      await abrirSesion(contexto.req, usuario);
      return usuario;
    },

    cerrarSesion: async (_, __, contexto) => {
      exigirSesion(contexto);
      await cerrarSesion(contexto.req, contexto.res);
      return true;
    },

    reservarPaquete: async (_, { input }, contexto) => {
      const usuario = exigirSesion(contexto);
      await limitar(`reserva:${usuario.id}`, 5, 60);
      if (input.pasajeros < 1 || input.pasajeros > 9) throw error('DATOS_INVALIDOS', 'Pasajeros: entre 1 y 9');
      return crearOrden(usuario.id, input);
    },
  },
};
