-- =============================================================================
-- Migration 007: Compartilhar a base de dados com outro usuário
-- Execute após a migration 006
-- =============================================================================

CREATE TABLE IF NOT EXISTS public.compartilhamentos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dono_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    dono_email TEXT NOT NULL,
    convidado_email TEXT NOT NULL,
    convidado_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'aceito')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_compartilhamentos_dono_convidado
    ON public.compartilhamentos (dono_id, lower(convidado_email));

CREATE INDEX IF NOT EXISTS idx_compartilhamentos_convidado_id
    ON public.compartilhamentos (convidado_id);

CREATE INDEX IF NOT EXISTS idx_compartilhamentos_convidado_email
    ON public.compartilhamentos (lower(convidado_email));

ALTER TABLE public.compartilhamentos ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "compartilhamentos_select" ON public.compartilhamentos;
DROP POLICY IF EXISTS "compartilhamentos_insert" ON public.compartilhamentos;
DROP POLICY IF EXISTS "compartilhamentos_update" ON public.compartilhamentos;
DROP POLICY IF EXISTS "compartilhamentos_delete" ON public.compartilhamentos;

CREATE POLICY "compartilhamentos_select" ON public.compartilhamentos
    FOR SELECT USING (
        auth.uid() = dono_id
        OR auth.uid() = convidado_id
        OR lower(convidado_email) = lower(COALESCE(auth.jwt() ->> 'email', ''))
    );

CREATE POLICY "compartilhamentos_insert" ON public.compartilhamentos
    FOR INSERT WITH CHECK (auth.uid() = dono_id);

CREATE POLICY "compartilhamentos_update" ON public.compartilhamentos
    FOR UPDATE USING (
        auth.uid() = dono_id
        OR auth.uid() = convidado_id
        OR lower(convidado_email) = lower(COALESCE(auth.jwt() ->> 'email', ''))
    );

CREATE POLICY "compartilhamentos_delete" ON public.compartilhamentos
    FOR DELETE USING (
        auth.uid() = dono_id
        OR auth.uid() = convidado_id
        OR lower(convidado_email) = lower(COALESCE(auth.jwt() ->> 'email', ''))
    );

GRANT SELECT, INSERT, UPDATE, DELETE ON public.compartilhamentos TO authenticated;

CREATE OR REPLACE FUNCTION public.pode_acessar_dados(dono uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
    SELECT dono IS NOT NULL AND (
        auth.uid() = dono
        OR EXISTS (
            SELECT 1
            FROM public.compartilhamentos c
            WHERE c.dono_id = dono
              AND c.status = 'aceito'
              AND c.convidado_id = auth.uid()
        )
    );
$$;

REVOKE ALL ON FUNCTION public.pode_acessar_dados(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.pode_acessar_dados(uuid) TO authenticated;

-- Clientes
DROP POLICY IF EXISTS "clientes_select_own" ON public.clientes;
DROP POLICY IF EXISTS "clientes_insert_own" ON public.clientes;
DROP POLICY IF EXISTS "clientes_update_own" ON public.clientes;
DROP POLICY IF EXISTS "clientes_delete_own" ON public.clientes;

CREATE POLICY "clientes_select_own" ON public.clientes
    FOR SELECT USING (public.pode_acessar_dados(user_id));
CREATE POLICY "clientes_insert_own" ON public.clientes
    FOR INSERT WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "clientes_update_own" ON public.clientes
    FOR UPDATE USING (public.pode_acessar_dados(user_id))
    WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "clientes_delete_own" ON public.clientes
    FOR DELETE USING (public.pode_acessar_dados(user_id));

-- Convênios
DROP POLICY IF EXISTS "convenios_select_own" ON public.convenios;
DROP POLICY IF EXISTS "convenios_insert_own" ON public.convenios;
DROP POLICY IF EXISTS "convenios_update_own" ON public.convenios;
DROP POLICY IF EXISTS "convenios_delete_own" ON public.convenios;

CREATE POLICY "convenios_select_own" ON public.convenios
    FOR SELECT USING (public.pode_acessar_dados(user_id));
CREATE POLICY "convenios_insert_own" ON public.convenios
    FOR INSERT WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "convenios_update_own" ON public.convenios
    FOR UPDATE USING (public.pode_acessar_dados(user_id))
    WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "convenios_delete_own" ON public.convenios
    FOR DELETE USING (public.pode_acessar_dados(user_id));

-- Remessas
DROP POLICY IF EXISTS "remessas_select_own" ON public.remessas;
DROP POLICY IF EXISTS "remessas_insert_own" ON public.remessas;
DROP POLICY IF EXISTS "remessas_update_own" ON public.remessas;
DROP POLICY IF EXISTS "remessas_delete_own" ON public.remessas;

CREATE POLICY "remessas_select_own" ON public.remessas
    FOR SELECT USING (public.pode_acessar_dados(user_id));
CREATE POLICY "remessas_insert_own" ON public.remessas
    FOR INSERT WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "remessas_update_own" ON public.remessas
    FOR UPDATE USING (public.pode_acessar_dados(user_id))
    WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "remessas_delete_own" ON public.remessas
    FOR DELETE USING (public.pode_acessar_dados(user_id));

-- titulos_valores
DROP POLICY IF EXISTS "titulos_valores_select_own" ON public.titulos_valores;
DROP POLICY IF EXISTS "titulos_valores_insert_own" ON public.titulos_valores;
DROP POLICY IF EXISTS "titulos_valores_update_own" ON public.titulos_valores;
DROP POLICY IF EXISTS "titulos_valores_delete_own" ON public.titulos_valores;

CREATE POLICY "titulos_valores_select_own" ON public.titulos_valores
    FOR SELECT USING (public.pode_acessar_dados(user_id));
CREATE POLICY "titulos_valores_insert_own" ON public.titulos_valores
    FOR INSERT WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "titulos_valores_update_own" ON public.titulos_valores
    FOR UPDATE USING (public.pode_acessar_dados(user_id))
    WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "titulos_valores_delete_own" ON public.titulos_valores
    FOR DELETE USING (public.pode_acessar_dados(user_id));

-- remessa_valores
DROP POLICY IF EXISTS "remessa_valores_select_own" ON public.remessa_valores;
DROP POLICY IF EXISTS "remessa_valores_insert_own" ON public.remessa_valores;
DROP POLICY IF EXISTS "remessa_valores_update_own" ON public.remessa_valores;
DROP POLICY IF EXISTS "remessa_valores_delete_own" ON public.remessa_valores;

CREATE POLICY "remessa_valores_select_own" ON public.remessa_valores
    FOR SELECT USING (public.pode_acessar_dados(user_id));
CREATE POLICY "remessa_valores_insert_own" ON public.remessa_valores
    FOR INSERT WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "remessa_valores_update_own" ON public.remessa_valores
    FOR UPDATE USING (public.pode_acessar_dados(user_id))
    WITH CHECK (public.pode_acessar_dados(user_id));
CREATE POLICY "remessa_valores_delete_own" ON public.remessa_valores
    FOR DELETE USING (public.pode_acessar_dados(user_id));
