# Guion de la demostración

Duración estimada: 12 a 15 minutos. Cubre los cuatro puntos que exige el enunciado:
(a) panel de Prefect, (b) tareas distribuidas en Dask, (c) consumo de GraphQL desde el frontend
y (d) fallo transaccional con compensaciones SAGA.

## Antes de empezar

1. Docker Desktop abierto y con internet.
2. Levantar el sistema y esperar a que todo esté sano:

   ```bash
   docker compose up -d
   ```

   ```bash
   docker compose ps
   ```

3. Abrir cuatro pestañas: http://localhost:3000, http://localhost:4200, http://localhost:8787 y el panel de Supabase.
4. Crear la cuenta de la demo en la aplicación (Iniciar sesión → Crear cuenta).

## 1. Arquitectura y Docker (2 min)

- Mostrar `docker compose ps`: 13 contenedores, todos arriba con un solo comando.
- Recorrer el diagrama de arquitectura del documento técnico.

## 2. Ingesta: Dask y Prefect — puntos (a) y (b) (4 min)

1. Lanzar la ingesta:

   ```bash
   docker compose exec flujos prefect deployment run ingesta/programada
   ```

2. **Panel de Dask** (`localhost:8787`, pestaña Status): las tareas se reparten entre los dos workers.
3. **Panel de Prefect** (`localhost:4200` → Runs → la ejecución de `ingesta`): 24 tareas, 12 de extracción y 12 de guardado.
4. Señalar una tarea con reintentos. La fuente de autos falla a propósito el 30 % de las veces,
   así que casi siempre hay alguna; abrirla y mostrar los intentos y la política (3 reintentos, esperas de 15, 45 y 120 s).
5. **Panel de Supabase** → Table Editor → `vuelos`: los datos reales y la columna `extraido_en` recién actualizada.

**Si Google limita las consultas:** las tareas de vuelos u hoteles agotan sus reintentos y el flow queda en rojo.
Es el comportamiento diseñado: mostrar que el error dice "posible límite de consultas", que las demás cadenas sí
guardaron y que el catálogo anterior sigue disponible en la aplicación.

## 3. GraphQL desde el frontend — punto (c) (3 min)

1. En la aplicación, buscar un paquete a Cartagena (6 al 9 de noviembre de 2026).
2. Abrir las herramientas del navegador → Red: una sola petición a `localhost:4000/graphql` trae vuelos, hoteles,
   autos y el paquete más económico.
3. Mostrar que la respuesta solo trae los campos pedidos (sin over-fetching).
4. Opcional, en Apollo Sandbox (`localhost:4000/graphql`): pedir solo `aerolinea` y `precioCop` y ver que no llega nada más.

## 4. SAGA: camino exitoso (2 min)

1. Con el selector de fallo en "Ninguno", pulsar **Reservar paquete**.
2. La pantalla de la orden avanza sola: Vuelo, Hotel, Auto y Pago pasan a "Hecho" y la orden queda **CONFIRMADA**.
3. Pulsar "Ver esta ejecución en el panel de Prefect": el flow `saga-<id>` en estado "Confirmada" con sus cuatro tareas.
4. En Supabase, mostrar que el inventario bajó (`cupos_disponibles` del vuelo elegido).

## 5. SAGA: fallo y compensaciones — punto (d) (3 min)

1. Buscar de nuevo y elegir **Simular fallo en: Reserva del auto**. Reservar.
2. En la pantalla de la orden:
   - Vuelo y Hotel se reservan; Auto falla.
   - Aparecen las compensaciones en orden inverso: auto, hotel, vuelo.
   - La orden queda **CANCELADA** con el motivo del fallo.
3. En Prefect: `reservar-auto` en rojo con 3 intentos, seguida de `cancelar-auto`, `cancelar-hotel` y `cancelar-vuelo` en verde.
   El flow queda en estado "Compensada".
4. En Supabase: el inventario del vuelo y del hotel volvió a su valor; en `reservas_vuelo` la fila quedó `CANCELADA`.
5. Variante si hay tiempo: fallo en **Cobro**, que además muestra la compensación del pago.

## 6. Seguridad (2 min)

- **Session Fixation:** herramientas del navegador → Aplicación → Cookies. Anotar el valor de `sid`, cerrar sesión,
  iniciar sesión de nuevo y mostrar que el valor cambió. La cookie es `HttpOnly`.
- **Hashing:** en Supabase, tabla `usuarios`: la columna `hash_contrasena` empieza por `$argon2id$`.
- **Rate limiting:** intentar iniciar sesión 6 veces con contraseña errada; el sexto intento responde
  "Demasiados intentos".
- **Cadena de suministro:** abrir `docs/seguridad/auditoria`: el reporte "antes" con la vulnerabilidad hallada
  en `virtualenv` y el "después" ya corregido.

## Preguntas probables

| Pregunta | Respuesta corta |
|---|---|
| ¿Por qué orquestación y no coreografía? | El enunciado pide que Prefect orqueste la SAGA; un orquestador central da además la trazabilidad en el panel. |
| ¿Qué pasa si falla una compensación? | Se reintenta 5 veces. Si aun así falla, el flow queda en rojo y la orden en `COMPENSANDO`, visible para intervención. |
| ¿Por qué no hay llaves foráneas entre servicios? | Cada servicio es dueño de sus tablas. Si la base garantizara la consistencia entre ellos, no haría falta la SAGA. |
| ¿Por qué autos es simulado? | Booking y Kayak bloquean navegadores automatizados y Google no ofrece autos. Evidencia en `docs/evidencia-scraping`. |
| ¿Cómo se evita reservar dos veces en un reintento? | Cada servicio es idempotente por `orden_id`, y la orden lleva una clave de idempotencia. |
