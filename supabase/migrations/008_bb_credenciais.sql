-- =============================================================================
-- Migration 008: Credenciais da API Cobranças BB por CNPJ (beneficiário)
-- Um CNPJ pode ter vários convênios; todos usam as mesmas credenciais.
-- Execute após a migration 007
-- =============================================================================

-- Se existir versão antiga (1 linha por usuário, sem CNPJ), remove e recria
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bb_credenciais'
          AND column_name = 'user_id'
    ) AND NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bb_credenciais'
          AND column_name = 'cnpj'
    ) THEN
        DROP TABLE public.bb_credenciais CASCADE;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.bb_credenciais (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    cnpj TEXT NOT NULL,
    razao_social TEXT,
    client_id TEXT NOT NULL,
    client_secret TEXT NOT NULL,
    app_key TEXT NOT NULL,
    ambiente TEXT NOT NULL DEFAULT 'homologacao'
        CHECK (ambiente IN ('sandbox', 'homologacao', 'producao')),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, cnpj)
);

CREATE INDEX IF NOT EXISTS idx_bb_credenciais_user_id ON public.bb_credenciais(user_id);
CREATE INDEX IF NOT EXISTS idx_bb_credenciais_cnpj ON public.bb_credenciais(cnpj);

ALTER TABLE public.bb_credenciais ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "bb_credenciais_select" ON public.bb_credenciais;
DROP POLICY IF EXISTS "bb_credenciais_insert" ON public.bb_credenciais;
DROP POLICY IF EXISTS "bb_credenciais_update" ON public.bb_credenciais;
DROP POLICY IF EXISTS "bb_credenciais_delete" ON public.bb_credenciais;

CREATE POLICY "bb_credenciais_select" ON public.bb_credenciais
    FOR SELECT USING (public.pode_acessar_dados(user_id));

CREATE POLICY "bb_credenciais_insert" ON public.bb_credenciais
    FOR INSERT WITH CHECK (public.pode_acessar_dados(user_id));

CREATE POLICY "bb_credenciais_update" ON public.bb_credenciais
    FOR UPDATE USING (public.pode_acessar_dados(user_id))
    WITH CHECK (public.pode_acessar_dados(user_id));

CREATE POLICY "bb_credenciais_delete" ON public.bb_credenciais
    FOR DELETE USING (public.pode_acessar_dados(user_id));

GRANT SELECT, INSERT, UPDATE, DELETE ON public.bb_credenciais TO authenticated;
