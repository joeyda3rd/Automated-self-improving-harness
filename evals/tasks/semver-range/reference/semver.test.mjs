import test from 'node:test';
import assert from 'node:assert';
import { compare, satisfies, maxSatisfying } from './semver.mjs';

test('precedence', () => {
  assert.strictEqual(compare('1.0.0-alpha', '1.0.0'), -1);
  assert.strictEqual(compare('1.0.0+a', '1.0.0+b'), 0);
  assert.throws(() => compare('1.2', '1.2.3'), TypeError);
});
test('ranges', () => {
  assert.ok(satisfies('0.0.3', '^0.0.3'));
  assert.ok(!satisfies('0.0.4', '^0.0.3'));
  assert.ok(satisfies('1.2.3-alpha.7', '>1.2.3-alpha.3'));
  assert.ok(!satisfies('3.4.5-alpha.9', '>1.2.3-alpha.3'));
  assert.strictEqual(maxSatisfying(['1.2.3', '1.2.4', '1.3.0'], '~1.2.0'), '1.2.4');
});
