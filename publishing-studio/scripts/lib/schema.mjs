import fs from 'node:fs';
import path from 'node:path';
import Ajv from 'ajv';
import { SCHEMAS_DIR } from './paths.mjs';

const ajv = new Ajv({ allErrors: true, strict: false });
const cache = new Map();

export function schemaValidator(name) {
  if (!cache.has(name)) {
    const schema = JSON.parse(fs.readFileSync(path.join(SCHEMAS_DIR, `${name}.schema.json`), 'utf8'));
    cache.set(name, ajv.compile(schema));
  }
  return cache.get(name);
}

/** Returns [{path, message}] (empty when valid). */
export function checkSchema(name, data) {
  const v = schemaValidator(name);
  if (v(data)) return [];
  return v.errors.map((e) => ({ path: e.instancePath || '/', message: `${e.message}${e.params?.additionalProperty ? ` (${e.params.additionalProperty})` : ''}${e.params?.allowedValues ? ` [${e.params.allowedValues.join(', ')}]` : ''}` }));
}
