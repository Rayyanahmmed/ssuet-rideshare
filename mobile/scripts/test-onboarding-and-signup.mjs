// Node test for pure app logic: onboarding checklist + signup student-ID rule.
// Run from mobile/:  node scripts/test-onboarding-and-signup.mjs
import { readFileSync, mkdirSync, rmSync, writeFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');
const require = createRequire(join(root, 'package.json'));
const ts = require('typescript');

function load(relPath) {
  const source = readFileSync(join(root, relPath), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2020 },
  });
  // Written inside the project so bare imports (zod) resolve from node_modules.
  const dir = join(root, 'scripts', '.tmp');
  mkdirSync(dir, { recursive: true });
  const out = join(dir, relPath.split('/').pop().replace(/\.ts$/, '.mjs'));
  writeFileSync(out, outputText);
  return import(pathToFileURL(out).href);
}

let passed = 0;
let failed = 0;
function check(name, fn) {
  try {
    fn();
    passed += 1;
    console.log(`PASS  ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL  ${name}\n      ${error.message}`);
  }
}
function eq(actual, expected, label = '') {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) throw new Error(`${label} expected ${e}, got ${a}`);
}

const onboarding = await load('src/lib/onboarding.ts');
const schemas = await load('src/lib/schemas.ts');
const { buildOnboardingSteps, nextOnboardingStep, onboardingProgress } = onboarding;
const { signupSchema } = schemas;

const fresh = { email_verified_at: null, verification_status: 'UNVERIFIED', role: 'STUDENT' };
const allDone = { email_verified_at: '2026-11-01T10:00:00Z', verification_status: 'VERIFIED', role: 'STUDENT' };

check('brand new member: first unfinished step is email', () => {
  const steps = buildOnboardingSteps(fresh, [], 0);
  eq(steps.map((s) => s.key), ['email', 'student_id', 'vehicle_added', 'vehicle_approved', 'first_ride']);
  eq(nextOnboardingStep(steps).key, 'email');
  eq(onboardingProgress(steps), { done: 0, total: 5, percent: 0 });
});

check('email done: next step is student ID with /verification route', () => {
  const steps = buildOnboardingSteps({ ...fresh, email_verified_at: '2026-11-01' }, [], 0);
  const next = nextOnboardingStep(steps);
  eq(next.key, 'student_id');
  eq(next.route, '/verification');
});

check('ID pending: step not done and detail says under review', () => {
  const steps = buildOnboardingSteps({ ...allDone, verification_status: 'PENDING' }, [], 0);
  const id = steps.find((s) => s.key === 'student_id');
  eq(id.done, false);
  eq(id.detail.includes('under review'), true, 'detail ');
});

check('ID rejected: action label says resubmit', () => {
  const steps = buildOnboardingSteps({ ...fresh, verification_status: 'REJECTED' }, [], 0);
  eq(steps.find((s) => s.key === 'student_id').actionLabel, 'Resubmit ID');
});

check('vehicle added but PENDING: next step is approval, route /vehicles', () => {
  const steps = buildOnboardingSteps(allDone, [{ status: 'PENDING' }], 0);
  const next = nextOnboardingStep(steps);
  eq(next.key, 'vehicle_approved');
  eq(next.route, '/vehicles');
});

check('vehicle approved but no ride: next step is publish', () => {
  const steps = buildOnboardingSteps(allDone, [{ status: 'VERIFIED' }], 0);
  const next = nextOnboardingStep(steps);
  eq(next.key, 'first_ride');
  eq(next.route, '/(tabs)/publish');
});

check('REJECTED vehicle does not count as approved', () => {
  const steps = buildOnboardingSteps(allDone, [{ status: 'REJECTED' }], 0);
  eq(steps.find((s) => s.key === 'vehicle_approved').done, false);
});

check('everything done: no next step, 100 percent', () => {
  const steps = buildOnboardingSteps(allDone, [{ status: 'VERIFIED' }], 2);
  eq(nextOnboardingStep(steps), null);
  eq(onboardingProgress(steps), { done: 5, total: 5, percent: 100 });
});

check('email step is an in-place action (route null)', () => {
  const steps = buildOnboardingSteps(fresh, [], 0);
  eq(steps[0].route, null);
  eq(steps[0].actionLabel, 'Resend email');
});

check('vehicle steps are marked driver-only, ID and email are not', () => {
  const steps = buildOnboardingSteps(fresh, [], 0);
  eq(steps.map((s) => s.driverOnly), [false, false, true, true, false]);
});

// ---- signup schema: student ID rule -------------------------------------------------
const base = {
  full_name: 'Ali Raza',
  email: 'ali.raza@ssuet.edu.pk',
  phone: '+923001234567',
  password: 'Password123',
  confirm_password: 'Password123',
  role: 'STUDENT',
  department: 'Computer Science',
  semester: '5',
};
const idError = (id, role = 'STUDENT') => {
  const result = signupSchema.safeParse({ ...base, role, university_id: id });
  if (result.success) return null;
  const issue = result.error.issues.find((i) => i.path[0] === 'university_id');
  return issue ? issue.message : null;
};

for (const good of ['2023F-Bcs-301', '2023s-bcs-045', ' 2024F-Se-120 ']) {
  check(`signup accepts student ID "${good}"`, () => {
    eq(idError(good), null, 'id-error ');
  });
}
for (const bad of ['SSUET-2022-101', '2023X-Bcs-301', '2023F-Bcs-30', '23F-Bcs-301', '2023F-Bcs-3011', 'abc']) {
  check(`signup rejects student ID "${bad}"`, () => {
    if (idError(bad) === null) throw new Error('expected an error for ' + bad);
  });
}
check('teacher employee ID stays free text (SSUET-EMP-1001 accepted)', () => {
  eq(idError('SSUET-EMP-1001', 'TEACHER'), null, 'teacher ');
});

// ---- password policy: any reasonable password is accepted ------------------------
const pwError = (password) => {
  const result = signupSchema.safeParse({ ...base, university_id: '2023F-Bcs-301', password, confirm_password: password });
  return result.success ? null : result.error.issues.find((i) => i.path[0] === 'password')?.message ?? 'other';
};
for (const good of ['a', 'abc', 'lettersonly', '12345678', 'password', '   spaces  ', 'x'.repeat(128)]) {
  check(`signup accepts password of length ${good.length}`, () => {
    eq(pwError(good), null, 'password-error ');
  });
}
for (const bad of ['', 'x'.repeat(129)]) {
  check(`signup rejects password of length ${bad.length}`, () => {
    if (pwError(bad) === null) throw new Error('expected rejection');
  });
}

console.log(`\n${passed} passed, ${failed} failed`);
rmSync(join(root, 'scripts', '.tmp'), { recursive: true, force: true });
process.exit(failed ? 1 : 0);
