-- ============================================================
-- Migration: Remove username column, enforce email-based auth
-- Run this in the Supabase SQL Editor (once).
-- All steps are idempotent — safe to run multiple times.
-- ============================================================

-- STEP 1: Drop the unique constraint on username (if still present)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE table_name = 'users'
          AND constraint_name = 'users_username_key'
    ) THEN
        ALTER TABLE public.users DROP CONSTRAINT users_username_key;
        RAISE NOTICE 'Dropped constraint users_username_key';
    ELSE
        RAISE NOTICE 'Constraint users_username_key does not exist -- skipping';
    END IF;
END
$$;

-- STEP 2: Drop the username column (if still present)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'username'
          AND table_schema = 'public'
    ) THEN
        ALTER TABLE public.users DROP COLUMN username;
        RAISE NOTICE 'Dropped column username';
    ELSE
        RAISE NOTICE 'Column username does not exist -- skipping';
    END IF;
END
$$;

-- STEP 3: Ensure email is NOT NULL
-- (fill any nulls with a safe placeholder first)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'users'
          AND column_name = 'email'
          AND is_nullable = 'YES'
          AND table_schema = 'public'
    ) THEN
        UPDATE public.users
        SET email = 'unknown_' || id::text || '@placeholder.invalid'
        WHERE email IS NULL;

        ALTER TABLE public.users ALTER COLUMN email SET NOT NULL;
        RAISE NOTICE 'email column set to NOT NULL';
    ELSE
        RAISE NOTICE 'email already NOT NULL -- skipping';
    END IF;
END
$$;

-- STEP 4: Add UNIQUE constraint on email (if missing)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.table_name = 'users'
          AND tc.constraint_type = 'UNIQUE'
          AND ccu.column_name = 'email'
          AND tc.table_schema = 'public'
    ) THEN
        ALTER TABLE public.users ADD CONSTRAINT users_email_key UNIQUE (email);
        RAISE NOTICE 'Added UNIQUE constraint on email';
    ELSE
        RAISE NOTICE 'UNIQUE constraint on email already exists -- skipping';
    END IF;
END
$$;

-- STEP 5: Ensure last_login column exists
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;

-- STEP 6: Ensure is_active column exists with safe default
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;

-- STEP 7: Upsert the admin user (email-only, no username)
-- ON CONFLICT on email so no duplicate is created.
INSERT INTO public.users (password_hash, full_name, email, role, is_active)
VALUES (
    '$2b$12$placeholder_overwritten_on_first_boot_xxxxxxxxxxxxxxxxxx',
    'Sumit Nayak',
    'sumitkumar.nayak@licious.com',
    'admin',
    TRUE
)
ON CONFLICT (email) DO UPDATE
    SET role = 'admin', is_active = TRUE;

-- ============================================================
-- Verify final schema
-- ============================================================
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'users' AND table_schema = 'public'
ORDER BY ordinal_position;
