/**
 * New-member setup checklist. Pure functions only (no React, no network) so the
 * step logic can be tested in isolation. The screen and the home card both read it.
 */

export type OnboardingUser = {
  email_verified_at?: string | null;
  verification_status: 'UNVERIFIED' | 'PENDING' | 'VERIFIED' | 'REJECTED';
  role: 'STUDENT' | 'TEACHER' | 'ADMIN';
};

export type OnboardingVehicle = { status: 'PENDING' | 'VERIFIED' | 'REJECTED' };

export type OnboardingStepKey = 'email' | 'student_id' | 'vehicle_added' | 'vehicle_approved' | 'first_ride';

export type OnboardingStep = {
  key: OnboardingStepKey;
  title: string;
  detail: string;
  done: boolean;
  /** Route the member should open next. `null` means the action happens on the checklist itself. */
  route: string | null;
  actionLabel: string;
  /** Only drivers need a vehicle; passengers can skip these two steps. */
  driverOnly: boolean;
};

export function buildOnboardingSteps(
  user: OnboardingUser,
  vehicles: OnboardingVehicle[],
  publishedRideCount: number,
): OnboardingStep[] {
  const idStatus = user.verification_status;
  const hasVehicle = vehicles.length > 0;
  const hasApprovedVehicle = vehicles.some((vehicle) => vehicle.status === 'VERIFIED');

  const idDetail =
    idStatus === 'VERIFIED'
      ? 'Your student ID is approved.'
      : idStatus === 'PENDING'
        ? 'Your ID is under review by the admin team.'
        : idStatus === 'REJECTED'
          ? 'The last submission was rejected. Upload a clear photo and resubmit.'
          : 'Upload your university ID card so the admin can verify you.';

  return [
    {
      key: 'email',
      title: 'Confirm your email',
      detail: user.email_verified_at
        ? 'Your email is confirmed.'
        : 'Open the confirmation email we sent you. Not received it? Tap resend.',
      done: Boolean(user.email_verified_at),
      route: null,
      actionLabel: 'Resend email',
      driverOnly: false,
    },
    {
      key: 'student_id',
      title: 'Verify your student ID',
      detail: idDetail,
      done: idStatus === 'VERIFIED',
      route: '/verification',
      actionLabel: idStatus === 'REJECTED' ? 'Resubmit ID' : 'Verify ID',
      driverOnly: false,
    },
    {
      key: 'vehicle_added',
      title: 'Add your vehicle',
      detail: hasVehicle ? 'Vehicle added.' : 'Add the car or bike you will drive (drivers only).',
      done: hasVehicle,
      route: '/vehicles',
      actionLabel: 'Add vehicle',
      driverOnly: true,
    },
    {
      key: 'vehicle_approved',
      title: 'Get your vehicle approved',
      detail: hasApprovedVehicle
        ? 'Your vehicle is approved.'
        : 'The admin checks your vehicle papers. This usually happens after you add it.',
      done: hasApprovedVehicle,
      route: '/vehicles',
      actionLabel: 'View vehicles',
      driverOnly: true,
    },
    {
      key: 'first_ride',
      title: 'Publish your first ride',
      detail: publishedRideCount > 0 ? 'You have published a ride.' : 'Once the steps above are done, publish a ride.',
      done: publishedRideCount > 0,
      route: '/(tabs)/publish',
      actionLabel: 'Publish ride',
      driverOnly: false,
    },
  ];
}

/** First step that is not done yet, or `null` when the checklist is complete. */
export function nextOnboardingStep(steps: OnboardingStep[]): OnboardingStep | null {
  return steps.find((step) => !step.done) ?? null;
}

export function onboardingProgress(steps: OnboardingStep[]): { done: number; total: number; percent: number } {
  const done = steps.filter((step) => step.done).length;
  const total = steps.length;
  return { done, total, percent: total === 0 ? 100 : Math.round((done / total) * 100) };
}
