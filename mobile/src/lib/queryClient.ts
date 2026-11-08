import { QueryClient } from '@tanstack/react-query';

/**
 * One cache for the whole app, in its own module so non-React code (the auth store) can drop
 * it: after a sign-out or an account switch, cached rides and messages must not survive.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Retrying a 401/403/422 only delays the error the member needs to see.
      retry: (failureCount, error) => {
        const code = (error as { code?: string } | null)?.code;
        if (
          code &&
          [
            'UNAUTHORIZED',
            'FORBIDDEN',
            'NOT_FOUND',
            'VALIDATION_ERROR',
            'ACCOUNT_NOT_VERIFIED',
            'ACCOUNT_SUSPENDED',
          ].includes(code)
        ) {
          return false;
        }
        return failureCount < 1;
      },
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

export function resetQueryCache(): void {
  queryClient.clear();
}
