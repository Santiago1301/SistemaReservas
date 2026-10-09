/**
 * Acceso al catálogo y a los usuarios a través del GraphQL nativo de Supabase
 * (pg_graphql). El gateway no abre conexiones SQL: toda su lectura de la base
 * pasa por esta API.
 */
import DataLoader from 'dataloader';
import { config, DESTINOS, ORIGEN } from './config.js';
import { error } from './errores.js';

async function consultar(query, variables = {}) {
  const respuesta = await fetch(`${config.supabaseUrl}/graphql/v1`, {
    method: 'POST',
    headers: { apikey: config.supabaseSecretKey, 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, variables }),
  });
  const cuerpo = await respuesta.json().catch(() => ({}));
  if (!respuesta.ok || cuerpo.errors) {
    console.error('Supabase GraphQL:', respuesta.status, JSON.stringify(cuerpo.errors ?? cuerpo).slice(0, 300));
    throw error('SERVICIO_NO_DISPONIBLE', 'No se pudo consultar el catálogo');
  }
  return cuerpo.data;
}

const nodos = (coleccion) => coleccion.edges.map((arista) => arista.node);

// Cómo se llama cada colección en pg_graphql y cómo se filtra y ordena.
const COLECCIONES = {
  vuelos: {
    nombre: 'vuelosCollection',
    precio: 'precioCop',
    filtro: (viaje) => ({
      origen: { eq: ORIGEN },
      destino: { eq: DESTINOS[viaje.destino] },
      fechaSalida: { eq: viaje.fechaInicio },
      cuposDisponibles: { gte: viaje.pasajeros },
    }),
    normalizar: (v) => ({
      ...v,
      ...(v.horaSalida && { horaSalida: v.horaSalida.slice(0, 5) }),
      ...(v.horaLlegada && { horaLlegada: v.horaLlegada.slice(0, 5) }),
    }),
  },
  hoteles: {
    nombre: 'hotelesCollection',
    precio: 'precioNocheCop',
    filtro: (viaje) => ({ ciudad: { eq: viaje.destino }, habitacionesDisponibles: { gte: 1 } }),
    // pg_graphql entrega los decimales como texto para no perder precisión.
    normalizar: (h) => ({ ...h, ...(h.puntuacion != null && { puntuacion: Number(h.puntuacion) }) }),
  },
  autos: {
    nombre: 'autosCollection',
    precio: 'precioDiaCop',
    filtro: (viaje) => ({ ciudad: { eq: viaje.destino }, unidadesDisponibles: { gte: 1 } }),
    normalizar: (a) => a,
  },
};

const TODOS_LOS_CAMPOS = {
  vuelos: 'id origen destino fechaSalida horaSalida horaLlegada aerolinea duracionMin escalas precioCop cuposDisponibles',
  hoteles: 'id nombre ciudad estrellas puntuacion precioNocheCop servicios habitacionesDisponibles',
  autos: 'id ciudad proveedor modelo categoria precioDiaCop unidadesDisponibles',
};

/** Fragmento de consulta para una colección: filtro por viaje, orden por precio. */
function fragmento(tipo, alias, campos, limite) {
  const { nombre, precio } = COLECCIONES[tipo];
  // Los nombres de campo vienen del esquema ya validado por Apollo, no de texto libre.
  const seleccion = [...new Set(['id', ...campos])].join(' ');
  return `${alias}: ${nombre}(filter: $${alias}, first: ${limite}, orderBy: [{${precio}: AscNullsLast}]) {
    edges { node { ${seleccion} } } }`;
}

const TIPO_FILTRO = { vuelos: 'VuelosFilter', hoteles: 'HotelesFilter', autos: 'AutosFilter' };

/**
 * Lista del catálogo para un viaje. `campos` son los que pidió el cliente: solo
 * esas columnas se le piden a la base (sin over-fetching de punta a punta).
 */
export async function listar(tipo, viaje, campos, limite) {
  const tope = Math.min(Math.max(limite, 1), 50);
  const datos = await consultar(
    `query($lista: ${TIPO_FILTRO[tipo]}) { ${fragmento(tipo, 'lista', campos, tope)} }`,
    { lista: COLECCIONES[tipo].filtro(viaje) },
  );
  return nodos(datos.lista).map(COLECCIONES[tipo].normalizar);
}

/** El más barato de cada tipo en una sola petición a Supabase. */
export async function masBaratos(viaje, camposPorTipo) {
  const tipos = Object.keys(COLECCIONES);
  const datos = await consultar(
    `query(${tipos.map((t) => `$${t}: ${TIPO_FILTRO[t]}`).join(', ')}) {
      ${tipos.map((t) => fragmento(t, t, [COLECCIONES[t].precio, ...camposPorTipo[t]], 1)).join('\n')}
    }`,
    Object.fromEntries(tipos.map((t) => [t, COLECCIONES[t].filtro(viaje)])),
  );
  const [vuelo, hotel, auto] = tipos.map((t) => nodos(datos[t]).map(COLECCIONES[t].normalizar)[0]);
  return vuelo && hotel && auto ? { vuelo, hotel, auto } : null;
}

/**
 * DataLoaders por petición: si se listan N órdenes, sus vuelos, hoteles y autos
 * se traen en 3 consultas agrupadas en vez de 3×N (problema N+1).
 */
export function crearLoaders() {
  const porIds = (tipo) =>
    new DataLoader(async (ids) => {
      const { nombre, normalizar } = COLECCIONES[tipo];
      const datos = await consultar(
        `query($ids: [UUID!]) { lista: ${nombre}(filter: {id: {in: $ids}}, first: ${ids.length}) {
          edges { node { ${TODOS_LOS_CAMPOS[tipo]} } } } }`,
        { ids },
      );
      const porId = new Map(nodos(datos.lista).map((fila) => [fila.id, normalizar(fila)]));
      return ids.map((id) => porId.get(id) ?? new Error(`No existe ${tipo} ${id}`));
    });
  return { vuelo: porIds('vuelos'), hotel: porIds('hoteles'), auto: porIds('autos') };
}

// ------------------------------------------------------------------ Usuarios
export async function buscarUsuario(email) {
  const datos = await consultar(
    `query($email: String!) { usuariosCollection(filter: {email: {eq: $email}}, first: 1) {
      edges { node { id email nombre hashContrasena } } } }`,
    { email },
  );
  return nodos(datos.usuariosCollection)[0] ?? null;
}

export async function crearUsuario({ email, nombre, hashContrasena }) {
  const datos = await consultar(
    `mutation($usuario: UsuariosInsertInput!) { insertIntoUsuariosCollection(objects: [$usuario]) {
      records { id email nombre } } }`,
    { usuario: { email, nombre, hashContrasena } },
  );
  return datos.insertIntoUsuariosCollection.records[0];
}
