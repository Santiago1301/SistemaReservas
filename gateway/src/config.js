function requerida(nombre) {
  const valor = process.env[nombre];
  if (!valor) throw new Error(`Falta la variable de entorno ${nombre}`);
  return valor;
}

export const config = {
  puerto: Number(process.env.PORT ?? 4000),
  supabaseUrl: requerida('SUPABASE_URL'),
  supabaseSecretKey: requerida('SUPABASE_SECRET_KEY'),
  sessionSecret: requerida('SESSION_SECRET'),
  ordenesUrl: process.env.ORDENES_URL ?? 'http://ordenes:8000',
  redisUrl: process.env.REDIS_URL ?? 'redis://redis:6379',
  origenFrontend: process.env.FRONTEND_ORIGIN ?? 'http://localhost:3000',
  prefectUiUrl: process.env.PREFECT_UI_URL ?? 'http://localhost:4200',
  // En producción (HTTPS) debe ser true para que la cookie no viaje en claro.
  cookieSegura: process.env.COOKIE_SECURE === 'true',
};

// Ciudad de destino -> aeropuerto. Los vuelos se guardan por código IATA.
export const ORIGEN = 'BOG';
export const DESTINOS = {
  'Cartagena de Indias': 'CTG',
  'Medellín': 'MDE',
  'Cali': 'CLO',
  'Santa Marta': 'SMR',
};
