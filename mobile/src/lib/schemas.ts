import { z } from 'zod';

/**
 * Zod schemas mirroring the backend Pydantic contracts (§26.9).
 * Same rules, same friendly messages — the API still validates everything.
 */

const passwordRules = z
  .string()
  .min(8, 'Use at least 8 characters')
  .regex(/[A-Za-z]/, 'Include at least one letter')
  .regex(/[0-9]/, 'Include at least one number');

export const loginSchema = z.object({
  email: z.string().min(1, 'Email is required').email('Enter a valid email address'),
  password: z.string().min(1, 'Password is required'),
});
export type LoginValues = z.infer<typeof loginSchema>;

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
    university_id: z.string().min(3, 'Student / employee ID is required').max(40),
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
