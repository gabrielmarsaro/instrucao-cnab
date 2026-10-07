-- =============================================================================
-- Migration 009: Credenciais BB — so o dono grava/altera/apaga
-- Convidados da base compartilhada ainda LEEM (para usar a API),
-- mas nao podem sobrescrever o client_secret do dono.
-- Execute apos 008_bb_credenciais.sql
-- =============================================================================

DROP POLICY IF EXISTS "bb_credenciais_insert" ON public.bb_credenciais;
DROP POLICY IF EXISTS "bb_credenciais_update" ON public.bb_credenciais;
DROP POLICY IF EXISTS "bb_credenciais_delete" ON public.bb_credenciais;

-- SELECT permanece com pode_acessar_dados (dono + convidados aceitos)
-- INSERT / UPDATE / DELETE: apenas o dono (auth.uid() = user_id)

CREATE POLICY "bb_credenciais_insert" ON public.bb_credenciais
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "bb_credenciais_update" ON public.bb_credenciais
    FOR UPDATE USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "bb_credenciais_delete" ON public.bb_credenciais
    FOR DELETE USING (auth.uid() = user_id);
