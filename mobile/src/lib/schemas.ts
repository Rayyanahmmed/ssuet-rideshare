import { z } from 'zod';

/**
 * Zod schemas mirroring the backend Pydantic contracts (§26.9).
 * Same rules, same friendly messages — the API still validates everything.
 */

// Members choose their own password: any text, not blank, at most 128 characters.
const passwordRules = z
  .string()
  .min(1, 'Enter a password')
  .max(128, 'Password must be at most 128 characters');

export const loginSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});
export type LoginValues = z.infer<typeof loginSchema>;

/** Fixed SSUET student ID: 4-digit year, F or S, programme letters, 3-digit roll. */
export const STUDENT_ID_REGEX = /^\d{4}[FS]-[A-Za-z]{2,6}-\d{3}$/i;
export const STUDENT_ID_HELP = 'Student ID must look like 2023F-Bcs-301 (year, F or S, programme, roll number)';

export const signupSchema = z
  .object({
    full_name: z.string().min(3, 'Enter your full name').max(120),
    email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
    phone: z
      .string()
      .min(10, 'Enter a valid phone number')
      .max(20)
      .regex(/^\+?[0-9\s-]+$/, 'Digits only, e.g. +923001234567'),
    password: passwordRules,
    confirm_password: z.string(),
    role: z.enum(['STUDENT', 'TEACHER']),
    university_id: z.string().trim().min(3, 'Student / employee ID is required').max(40),
    department: z.string().min(2, 'Select your department'),
    home_area: z.string().max(160).optional(),
    semester: z.string().trim().max(2, 'Semester is a number from 1 to 12').optional(),
    designation: z.string().max(120).optional(),
  })
  .refine((values) => values.password === values.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  })
  .refine(
    (values) => values.role !== 'STUDENT' || Boolean(values.semester && values.semester.length > 0),
    { path: ['semester'], message: 'Select your current semester (1 – 12)' },
  )
  // The API rejects anything outside 1–12 with a generic 422, so catch it here first and
  // say exactly what is wrong instead of letting the member guess (§21).
  .refine(
    (values) => {
      const raw = values.semester?.trim();
      if (!raw) return true;
      if (!/^\d{1,2}$/.test(raw)) return false;
      const semester = Number(raw);
      return semester >= 1 && semester <= 12;
    },
    { path: ['semester'], message: 'Semester must be a whole number from 1 to 12' },
  )
  // Students: fixed SSUET roll format, e.g. 2023F-Bcs-301 (year, F/S, programme, 3-digit roll).
  // Mirrors backend/app/schemas/auth.py STUDENT_ID_PATTERN. Teachers keep free-text employee IDs.
  .refine(
    (values) => values.role !== 'STUDENT' || STUDENT_ID_REGEX.test(values.university_id.trim()),
    { path: ['university_id'], message: STUDENT_ID_HELP },
  );
export type SignupValues = z.infer<typeof signupSchema>;

export const forgotPasswordSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
});
export type ForgotPasswordValues = z.infer<typeof forgotPasswordSchema>;

export const resetPasswordSchema = z
  .object({
    token: z.string().trim().min(20, 'Enter the reset code exactly as it was sent to you'),
    password: passwordRules,
    confirm_password: z.string(),
  })
  .refine((values) => values.password === values.confirm_password, {
    path: ['confirm_password'],
    message: 'Passwords do not match',
  });
export type ResetPasswordValues = z.infer<typeof resetPasswordSchema>;

export const DEPARTMENTS = [
  'Computer Science',
  'Software Engineering',
  'Electrical Engineering',
  'Electronic Engineering',
  'Civil Engineering',
  'Biomedical Engineering',
  'Business Administration',
  'Basic Sciences',
] as const;

/**
 * Common Karachi pickup areas.
 *
 * The map screen lets a member drop an exact pin; these names keep search and
 * publishing usable when no Google Maps key is configured (§13) and give the API a
 * human-readable area label to show before a match.
 */
export const KARACHI_AREAS = [
  'Gulshan-e-Iqbal',
  'Gulistan-e-Johar',
  'North Nazimabad',
  'Federal B Area',
  'PECHS',
  'Clifton',
  'Saddar',
  'Scheme 33',
  'Malir',
  'Korangi',
  'Gulberg',
  'Liaquatabad',
] as const;
