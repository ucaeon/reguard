ALTER TABLE recalls ADD COLUMN revision BIGINT NOT NULL DEFAULT 1;
CREATE FUNCTION bump_recall_revision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF ROW(NEW.product_name,NEW.company_name,NEW.reason,NEW.action_method,NEW.target_conditions,
           NEW.source_url,NEW.image_url,NEW.source_created_at,NEW.raw_payload)
       IS DISTINCT FROM
       ROW(OLD.product_name,OLD.company_name,OLD.reason,OLD.action_method,OLD.target_conditions,
           OLD.source_url,OLD.image_url,OLD.source_created_at,OLD.raw_payload) THEN
        NEW.revision := OLD.revision + 1;
    ELSE
        NEW.revision := OLD.revision;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER recalls_revision BEFORE UPDATE ON recalls
FOR EACH ROW EXECUTE FUNCTION bump_recall_revision();
