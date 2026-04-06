CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nome TEXT,
    username_instagram TEXT NOT NULL,
    mensagem TEXT NOT NULL,
    nicho_detectado TEXT,
    resumo_ia TEXT,
    confianca_ia FLOAT DEFAULT 0,
    data_criacao TIMESTAMPTZ DEFAULT NOW(),
    status TEXT DEFAULT 'novo',
    origem TEXT DEFAULT 'instagram_dm',
    observacoes TEXT,
    atualizado_em TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_nicho_detectado ON leads(nicho_detectado);
CREATE INDEX IF NOT EXISTS idx_leads_username_instagram ON leads(username_instagram);
CREATE INDEX IF NOT EXISTS idx_leads_data_criacao ON leads(data_criacao);

CREATE OR REPLACE FUNCTION leads_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_leads_update_timestamp ON leads;
CREATE TRIGGER trigger_leads_update_timestamp
BEFORE UPDATE ON leads
FOR EACH ROW
EXECUTE FUNCTION leads_update_timestamp();

CREATE OR REPLACE VIEW leads_novos AS
SELECT *
FROM leads
WHERE status = 'novo';

CREATE OR REPLACE VIEW leads_por_nicho AS
SELECT nicho_detectado,
       COUNT(*) AS total_leads
FROM leads
GROUP BY nicho_detectado
ORDER BY total_leads DESC;
