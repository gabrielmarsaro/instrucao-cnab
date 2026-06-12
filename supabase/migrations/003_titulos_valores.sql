-- =============================================================================
-- Migration 003: Valor nominal registrado por título (após instrução 47)
-- Execute após a migration 002
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.titulos_valores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    convenio_id UUID NOT NULL REFERENCES public.convenios(id) ON DELETE CASCADE,
    nosso_numero TEXT NOT NULL,
    seu_numero TEXT,
    valor_nominal NUMERIC(15, 2) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, convenio_id, nosso_numero)
);

CREATE INDEX IF NOT EXISTS idx_titulos_valores_lookup
    ON public.titulos_valores(user_id, convenio_id);

ALTER TABLE public.titulos_valores ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "titulos_valores_select_own" ON public.titulos_valores;
DROP POLICY IF EXISTS "titulos_valores_insert_own" ON public.titulos_valores;
DROP POLICY IF EXISTS "titulos_valores_update_own" ON public.titulos_valores;
DROP POLICY IF EXISTS "titulos_valores_delete_own" ON public.titulos_valores;

CREATE POLICY "titulos_valores_select_own" ON public.titulos_valores
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "titulos_valores_insert_own" ON public.titulos_valores
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "titulos_valores_update_own" ON public.titulos_valores
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "titulos_valores_delete_own" ON public.titulos_valores
    FOR DELETE USING (auth.uid() = user_id);
