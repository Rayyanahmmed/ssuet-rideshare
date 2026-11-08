import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from './client';
import { useAdminAuth } from '@/store/auth';

export type Health = { status: string; version: string; environment: string };
export type Meta = {
  university: { name: string; short_name: string; latitude: number; longitude: number; default_area_label: string };
  features: { maps_configured: boolean; push_notifications: boolean; max_confirmed_passengers: number };
  environment: string;
};

export const useHealth = () =>
  useQuery({ queryKey: ['health'], queryFn: async () => (await api.get<Health>('/health')).data, refetchInterval: 30_000 });

export const useReady = () =>
  useQuery({ queryKey: ['ready'], queryFn: async () => (await api.get('/health/ready')).data, retry: 0 });

export const useMeta = () =>
  useQuery({ queryKey: ['meta'], queryFn: async () => (await api.get<Meta>('/meta')).data });

export type LoginResponse = {
  access_token: string;
  refresh_token: string;
  user: { id: string; full_name: string; email: string; role: string; department: string; account_status: string };
};

/** Admin login: the API is the authority — a non-admin token is rejected here. */
export const useLogin = () =>
  useMutation({
    mutationFn: async (credentials: { email: string; password: string }) => {
      const { data } = await api.post<LoginResponse>('/auth/login', credentials);
      if (data.user.role !== 'ADMIN') {
        throw new Error('This account does not have administrator access.');
      }
      return data;
    },
    onSuccess: (data) => {
      useAdminAuth.getState().setSession(
        data.user as Parameters<ReturnType<typeof useAdminAuth.getState>['setSession']>[0],
        data.access_token,
        data.refresh_token,
      );
    },
  });

export const useMe = (enabled: boolean) =>
  useQuery({
    queryKey: ['me'],
    enabled,
    queryFn: async () => (await api.get('/auth/me')).data,
    retry: 0,
  });
