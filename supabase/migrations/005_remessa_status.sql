-- =============================================================================
-- Migration 005: Status da remessa (gerada / aceita / rejeitada) + NSA por convênio
-- Execute após a migration 004
-- =============================================================================

ALTER TABLE public.remessas
    ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'gerada';

CREATE INDEX IF NOT EXISTS idx_remessas_convenio_id ON public.remessas(convenio_id);

DROP POLICY IF EXISTS "remessas_update_own" ON public.remessas;

CREATE POLICY "remessas_update_own" ON public.remessas
    FOR UPDATE USING (auth.uid() = user_id);
