-- =============================================================================
-- Migration 006: Guardar o arquivo CNAB completo para re-download no histórico
-- Execute após a migration 005
-- =============================================================================

ALTER TABLE public.remessas
    ADD COLUMN IF NOT EXISTS arquivo_b64 TEXT;
