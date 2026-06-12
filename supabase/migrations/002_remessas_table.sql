-- =============================================================================
-- Migration 002: Histórico de remessas geradas
-- Execute após a migration 001
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.remessas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    convenio_id UUID REFERENCES public.convenios(id) ON DELETE SET NULL,
    nome_arquivo TEXT NOT NULL,
    total_lotes INTEGER NOT NULL DEFAULT 0,
    total_boletos INTEGER NOT NULL DEFAULT 0,
    instrucoes JSONB DEFAULT '[]'::jsonb,
    preview_linhas JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_remessas_user_id ON public.remessas(user_id);
CREATE INDEX IF NOT EXISTS idx_remessas_created_at ON public.remessas(created_at DESC);

ALTER TABLE public.remessas ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "remessas_select_own" ON public.remessas;
DROP POLICY IF EXISTS "remessas_insert_own" ON public.remessas;
DROP POLICY IF EXISTS "remessas_delete_own" ON public.remessas;

CREATE POLICY "remessas_select_own" ON public.remessas
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "remessas_insert_own" ON public.remessas
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "remessas_delete_own" ON public.remessas
    FOR DELETE USING (auth.uid() = user_id);
