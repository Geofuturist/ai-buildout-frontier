import lineModule from './line';
import pointModule from './point';
import polygonModule from './polygon';
import type { GeometryModule, GeometryType } from './types';

// A new geometry kind = a new module here; nothing else changes.
export const MODULES: GeometryModule[] = [polygonModule, lineModule, pointModule];

export const MODULE_BY_TYPE = Object.fromEntries(MODULES.map((m) => [m.type, m])) as Record<GeometryType, GeometryModule>;
export type { GeometryModule, GeometryType, ModuleCtx } from './types';
