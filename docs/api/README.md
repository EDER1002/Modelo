# Especificación de la API · SismoSantander

Contrato entre el backend (este repositorio) y el frontend React de SismoSantander.

| # | Entregable | Documento |
|---|---|---|
| 1 | Resumen de los requerimientos detectados | [api-requirements.md §1](api-requirements.md#1-resumen-de-los-requerimientos-detectados) |
| 2 | Inventario de variables disponibles y derivadas | [api-requirements.md §2](api-requirements.md#2-inventario-de-variables) |
| 3 | Fuentes oficiales verificadas y sus limitaciones | [api-requirements.md §3](api-requirements.md#3-fuentes-oficiales-verificación-y-limitaciones) |
| 4 | Arquitectura recomendada | [data-model.md §1](data-model.md#1-arquitectura-recomendada) |
| 5 | Modelo de datos | [data-model.md §2–9](data-model.md#2-entidades-y-relaciones) |
| 6 | Catálogo completo de endpoints | [api-endpoints.md §2](api-endpoints.md#2-catálogo-de-endpoints-entregable-6) |
| 7 | Contrato JSON de cada endpoint | [api-endpoints.md §3](api-endpoints.md#3-contratos-por-endpoint-entregable-7) |
| 8 | Matriz de integración con las páginas | [frontend-integration.md §2](frontend-integration.md#2-matriz-de-integración-por-página-entregable-8) |
| 9 | Interfaces TypeScript | [frontend-integration.md §3](frontend-integration.md#3-interfaces-typescript-entregable-9) |
| 10 | Estrategia de filtros globales | [api-endpoints.md §1](api-endpoints.md#1-filtros-globales-entregable-10) |
| 11 | Manejo de errores | [api-endpoints.md §4](api-endpoints.md#4-manejo-de-errores-entregable-11) |
| 12 | Seguridad y rendimiento | [api-endpoints.md §5](api-endpoints.md#5-seguridad-y-rendimiento-entregable-12) |
| 13 | Especificación OpenAPI 3.1 | `openapi.yaml` — **pendiente** |
| 14 | Archivos del backend | [frontend-integration.md §5](frontend-integration.md#5-archivos-que-se-deben-crear-en-el-backend-entregable-14) |
| 15 | Plan de implementación por fases | [frontend-integration.md §6](frontend-integration.md#6-plan-de-implementación-por-fases) |
| 16 | Preguntas y decisiones pendientes | [api-requirements.md §4](api-requirements.md#4-preguntas-y-decisiones-pendientes-entregable-16) |

**Estado:** especificación. Hoy funciona `api.py` (rutas en español, ver `API.md` en la raíz), que sirve el modelo.
Las rutas `/api/v1/...` de esta especificación se implementan por fases.
