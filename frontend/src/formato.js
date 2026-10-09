const pesos = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'COP', maximumFractionDigits: 0 });
const fechaLarga = new Intl.DateTimeFormat('es-CO', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
const horaCorta = new Intl.DateTimeFormat('es-CO', { hour: '2-digit', minute: '2-digit', second: '2-digit' });

export const dinero = (valor) => pesos.format(valor);
export const fecha = (iso) => fechaLarga.format(new Date(iso));
export const hora = (iso) => horaCorta.format(new Date(iso));

export function duracion(minutos) {
  if (!minutos) return '';
  const h = Math.floor(minutos / 60);
  const m = minutos % 60;
  return h ? `${h} h ${m} min` : `${m} min`;
}

export const noches = (inicio, fin) => Math.round((Date.parse(fin) - Date.parse(inicio)) / 86_400_000);

/** Mensaje legible de un error de Apollo (el gateway ya los entrega en español). */
export const mensajeDe = (error) => error?.errors?.[0]?.message ?? error?.message ?? 'Ocurrió un error';
