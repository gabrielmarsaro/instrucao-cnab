-- =============================================================================
-- Migration 001: Tabelas base + RLS (clientes, convenios)
-- Execute no SQL Editor do Supabase (Dashboard → SQL → New query)
-- =============================================================================

-- Clientes (caso ainda não exista)
CREATE TABLE IF NOT EXISTS public.clientes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    id_cliente_planilha TEXT,
    cnpj_cpf TEXT,
    nome TEXT,
    endereco TEXT,
    bairro TEXT,
    cep TEXT,
    cidade TEXT,
    uf TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Convênios (caso ainda não exista)
CREATE TABLE IF NOT EXISTS public.convenios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    cnpj TEXT,
    razao_social TEXT,
    agencia TEXT,
    dv_agencia TEXT,
    conta TEXT,
    dv_conta TEXT,
    convenio TEXT,
    carteira TEXT,
    variacao TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_clientes_user_id ON public.clientes(user_id);
CREATE INDEX IF NOT EXISTS idx_convenios_user_id ON public.convenios(user_id);

-- RLS: clientes
ALTER TABLE public.clientes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "clientes_select_own" ON public.clientes;
DROP POLICY IF EXISTS "clientes_insert_own" ON public.clientes;
DROP POLICY IF EXISTS "clientes_update_own" ON public.clientes;
DROP POLICY IF EXISTS "clientes_delete_own" ON public.clientes;

CREATE POLICY "clientes_select_own" ON public.clientes
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "clientes_insert_own" ON public.clientes
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "clientes_update_own" ON public.clientes
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "clientes_delete_own" ON public.clientes
    FOR DELETE USING (auth.uid() = user_id);

-- RLS: convenios
ALTER TABLE public.convenios ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "convenios_select_own" ON public.convenios;
DROP POLICY IF EXISTS "convenios_insert_own" ON public.convenios;
DROP POLICY IF EXISTS "convenios_update_own" ON public.convenios;
DROP POLICY IF EXISTS "convenios_delete_own" ON public.convenios;

CREATE POLICY "convenios_select_own" ON public.convenios
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "convenios_insert_own" ON public.convenios
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "convenios_update_own" ON public.convenios
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "convenios_delete_own" ON public.convenios
    FOR DELETE USING (auth.uid() = user_id);
