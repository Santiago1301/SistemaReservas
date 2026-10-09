/** Cliente del servicio de órdenes. El gateway no toca sus tablas: le habla por HTTP. */
import { config } from './config.js';
import { error } from './errores.js';

async function llamar(ruta, opciones = {}) {
  let respuesta;
  try {
    respuesta = await fetch(`${config.ordenesUrl}${ruta}`, {
      ...opciones,
      headers: { 'Content-Type': 'application/json' },
      signal: AbortSignal.timeout(30_000),
    });
  } catch {
    throw error('SERVICIO_NO_DISPONIBLE', 'El servicio de órdenes no responde');
  }
  if (respuesta.status === 404) return null;
  const cuerpo = await respuesta.json().catch(() => ({}));
  if (respuesta.ok) return cuerpo;
  if (respuesta.status < 500) {
    const detalle = typeof cuerpo.detail === 'string' ? cuerpo.detail : 'Los datos de la reserva no son válidos';
    throw error('DATOS_INVALIDOS', detalle);
  }
  throw error('SERVICIO_NO_DISPONIBLE', 'No se pudo procesar la orden en este momento');
}

/** Traduce la orden del servicio (snake_case) a la forma del esquema GraphQL. */
function aOrden(o) {
  return {
    id: o.id,
    usuarioId: o.usuario_id,
    estado: o.estado,
    totalCop: o.total_cop,
    motivoFallo: o.motivo_fallo,
    fechaInicio: o.fecha_inicio,
    fechaFin: o.fecha_fin,
    pasajeros: o.pasajeros,
    vueloId: o.vuelo_id,
    hotelId: o.hotel_id,
    autoId: o.auto_id,
    flowRunId: o.flow_run_id,
    creadoEn: o.creado_en,
    // Solo vienen al consultar una orden puntual, no en el listado.
    pago: o.pago,
    pasos: o.pasos?.map((p) => ({ ...p, creadoEn: p.creado_en })),
  };
}

export async function crearOrden(usuarioId, input) {
  const orden = await llamar('/ordenes', {
    method: 'POST',
    body: JSON.stringify({
      usuario_id: usuarioId,
      vuelo_id: input.vueloId,
      hotel_id: input.hotelId,
      auto_id: input.autoId,
      fecha_inicio: input.fechaInicio,
      fecha_fin: input.fechaFin,
      pasajeros: input.pasajeros,
      clave_idempotencia: input.claveIdempotencia,
      simular_fallo_en: input.simularFalloEn ?? null,
    }),
  });
  if (!orden) throw error('DATOS_INVALIDOS', 'El vuelo, hotel o auto elegido ya no existe');
  return aOrden(orden);
}

export async function obtenerOrden(id) {
  const orden = await llamar(`/ordenes/${encodeURIComponent(id)}`);
  return orden && aOrden(orden);
}

export async function listarOrdenes(usuarioId) {
  const ordenes = await llamar(`/ordenes?usuario_id=${encodeURIComponent(usuarioId)}`);
  return (ordenes ?? []).map(aOrden);
}
