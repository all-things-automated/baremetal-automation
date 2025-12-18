-- PostgreSQL trigger for Kea DHCP lease NOTIFY/LISTEN
-- Enables event-driven lease processing via pg_notify()

-- Create notification function
CREATE OR REPLACE FUNCTION kea_lease_notify()
RETURNS trigger AS $$
DECLARE
    notification_payload TEXT;
    lease_address TEXT;
BEGIN
    IF (TG_OP = 'DELETE') THEN
        lease_address := host(OLD.address + '0.0.0.0'::inet);
        notification_payload := lease_address || ':' || 
                               COALESCE(encode(OLD.hwaddr, 'hex'), '') || ':' ||
                               COALESCE(OLD.hostname, '');
    ELSE
        lease_address := host(NEW.address + '0.0.0.0'::inet);
        notification_payload := lease_address || ':' || 
                               COALESCE(encode(NEW.hwaddr, 'hex'), '') || ':' ||
                               COALESCE(NEW.hostname, '');
    END IF;
    
    PERFORM pg_notify('kea_lease_events', notification_payload);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Create trigger on lease4 table
DROP TRIGGER IF EXISTS kea_lease_notify_trigger ON lease4;
CREATE TRIGGER kea_lease_notify_trigger
AFTER INSERT OR UPDATE OF address, hwaddr, hostname ON lease4
FOR EACH ROW
EXECUTE FUNCTION kea_lease_notify();

CREATE INDEX IF NOT EXISTS lease4_hwaddr_idx ON lease4 (hwaddr);
CREATE INDEX IF NOT EXISTS lease4_hostname_idx ON lease4 (hostname);
