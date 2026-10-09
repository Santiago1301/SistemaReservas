import { GraphQLError } from 'graphql';

const ESTADO_HTTP = { NO_AUTENTICADO: 401, DATOS_INVALIDOS: 400, LIMITE_EXCEDIDO: 429, SERVICIO_NO_DISPONIBLE: 503 };

/** Error de GraphQL con un código estable para que el frontend reaccione. */
export function error(codigo, mensaje) {
  return new GraphQLError(mensaje, { extensions: { code: codigo, http: { status: ESTADO_HTTP[codigo] } } });
}
