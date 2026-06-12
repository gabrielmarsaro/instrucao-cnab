-- =============================================================================
-- Migration 004: Snapshot dos valores enviados em cada remessa
-- Execute após a migration 003
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.remessa_valores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    remessa_id UUID NOT NULL REFERENCES public.remessas(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    convenio_id UUID NOT NULL REFERENCES public.convenios(id) ON DELETE CASCADE,
    nosso_numero TEXT NOT NULL,
    seu_numero TEXT,
    valor_nominal NUMERIC(15, 2) NOT NULL,
    cod_instrucao TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (remessa_id, nosso_numero)
);

CREATE INDEX IF NOT EXISTS idx_remessa_valores_remessa_id ON public.remessa_valores(remessa_id);
CREATE INDEX IF NOT EXISTS idx_remessa_valores_convenio ON public.remessa_valores(user_id, convenio_id);

ALTER TABLE public.remessa_valores ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "remessa_valores_select_own" ON public.remessa_valores;
DROP POLICY IF EXISTS "remessa_valores_insert_own" ON public.remessa_valores;
DROP POLICY IF EXISTS "remessa_valores_update_own" ON public.remessa_valores;
DROP POLICY IF EXISTS "remessa_valores_delete_own" ON public.remessa_valores;

CREATE POLICY "remessa_valores_select_own" ON public.remessa_valores
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "remessa_valores_insert_own" ON public.remessa_valores
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "remessa_valores_update_own" ON public.remessa_valores
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "remessa_valores_delete_own" ON public.remessa_valores
    FOR DELETE USING (auth.uid() = user_id);
