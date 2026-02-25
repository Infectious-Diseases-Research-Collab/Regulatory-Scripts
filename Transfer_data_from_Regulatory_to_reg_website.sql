/*
===============================================================================
Transfer data from Regulatory to reg_website
===============================================================================
This script moves data from the old database (Regulatory) to the new database
(reg_website). The tables already exist in the reg_website database.

Strategy:
  - Some tables need no changes (just keep existing data)
  - Some tables need to be truncated (fresh start, no import)
  - Some tables need to be truncated and re-imported from Regulatory
  - irb_submissions is imported from projectbodies with field mapping

Because SQL Server won't allow TRUNCATE on tables referenced by FK constraints
(even when the child table is empty), we drop all relevant FKs first, do the
truncation and import, then re-add the FKs with WITH CHECK.
===============================================================================
*/

USE [reg_website]
GO

SET NOCOUNT ON;
SET XACT_ABORT ON;

/*
===============================================================================
Tables that do NOT need any changes (leave as-is):
  - tblUsers
  - tblNaviTabs
  - tblTopTabs
  - expirystatus
  - document_categories
===============================================================================
*/

/*
===============================================================================
Phase 1: Drop FK constraints that block truncation
===============================================================================
*/
PRINT '--- Phase 1: Dropping FK constraints ---';

-- sample_tracking FKs
ALTER TABLE sample_tracking DROP CONSTRAINT FK_sample_tracking_mta_tracking;
ALTER TABLE sample_tracking DROP CONSTRAINT FK_sample_tracking_sample_types;

-- mta_tracking FKs
ALTER TABLE mta_tracking DROP CONSTRAINT FK_mta_tracking_mta_institutions;
ALTER TABLE mta_tracking DROP CONSTRAINT FK_mta_tracking_projects;
ALTER TABLE mta_tracking DROP CONSTRAINT FK_mta_tracking_regbodies;

-- informed_consents FKs
ALTER TABLE informed_consents DROP CONSTRAINT FK_informed_consents_projects;
ALTER TABLE informed_consents DROP CONSTRAINT FK_informed_consents_regbodies;

-- irb_submissions FKs
ALTER TABLE irb_submissions DROP CONSTRAINT FK_irb_submissions_projects;
ALTER TABLE irb_submissions DROP CONSTRAINT FK_irb_submissions_regbodies;

-- project_documents FKs
ALTER TABLE project_documents DROP CONSTRAINT FK_project_documents_projects;

-- projectemails FKs
ALTER TABLE projectemails DROP CONSTRAINT FK_projectemails_projects;
ALTER TABLE projectemails DROP CONSTRAINT FK_projectemails_emails;

-- monitoring FKs
ALTER TABLE monitoring DROP CONSTRAINT FK_monitoring_projects;

-- training FKs
ALTER TABLE training DROP CONSTRAINT FK_training_projects;

-- sae FKs
ALTER TABLE sae DROP CONSTRAINT [FK__sae__project__0B5CAFEA];

PRINT 'All FK constraints dropped.';


/*
===============================================================================
Phase 2: Truncate tables
===============================================================================
*/
PRINT '--- Phase 2: Truncating tables ---';

-- Tables that only need truncation (no re-import)
TRUNCATE TABLE sample_tracking;
TRUNCATE TABLE mta_tracking;
TRUNCATE TABLE mta_institutions;
TRUNCATE TABLE sample_types;
TRUNCATE TABLE informed_consents;
TRUNCATE TABLE project_documents;
TRUNCATE TABLE monitoring;
TRUNCATE TABLE training;
TRUNCATE TABLE sae;
TRUNCATE TABLE investigators;
TRUNCATE TABLE investigator_documents;
TRUNCATE TABLE students;
TRUNCATE TABLE student_documents;
TRUNCATE TABLE audit_log;
TRUNCATE TABLE tblAccessLog;

-- Tables that need truncation AND re-import from Regulatory
TRUNCATE TABLE irb_submissions;
TRUNCATE TABLE projectemails;
TRUNCATE TABLE projects;
TRUNCATE TABLE regbodies;
TRUNCATE TABLE emails;

PRINT 'All tables truncated.';


/*
===============================================================================
Phase 3: Re-import data from Regulatory
===============================================================================
*/
PRINT '--- Phase 3: Importing data from Regulatory ---';

BEGIN TRY
    BEGIN TRAN;

    /* 1) Base / lookup tables (no dependencies) */
    PRINT '  projects';
    INSERT INTO reg_website.dbo.projects (project, regulatory_binder_status)
    SELECT s.project, 'Does not Exist'
    FROM Regulatory.dbo.projects AS s
    WHERE NOT EXISTS (
        SELECT 1 FROM reg_website.dbo.projects AS t
        WHERE t.project = s.project
    );

    PRINT '  regbodies';
    INSERT INTO reg_website.dbo.regbodies (regbody)
    SELECT s.regbody
    FROM Regulatory.dbo.regbodies AS s
    WHERE NOT EXISTS (
        SELECT 1 FROM reg_website.dbo.regbodies AS t
        WHERE t.regbody = s.regbody
    );

    PRINT '  emails';
    INSERT INTO reg_website.dbo.emails (emailaddress)
    SELECT s.emailaddress
    FROM Regulatory.dbo.emails AS s
    WHERE NOT EXISTS (
        SELECT 1 FROM reg_website.dbo.emails AS t
        WHERE t.emailaddress = s.emailaddress
    );

    /* 2) Child tables (depend on projects, emails) */
    PRINT '  projectemails';
    INSERT INTO reg_website.dbo.projectemails (project, emailaddress)
    SELECT s.project, s.emailaddress
    FROM Regulatory.dbo.projectemails AS s
    WHERE NOT EXISTS (
        SELECT 1 FROM reg_website.dbo.projectemails AS t
        WHERE t.project = s.project AND t.emailaddress = s.emailaddress
    );

    /* 3) irb_submissions (mapped from projectbodies)
       Field mapping:
         submission_id     - identity, auto-populated
         irb_number        - default 'UNKNOWN'
         submission_type   - default 'Initial'
         protocol_version  - NULL
         protocol_version_date - NULL
         approval_date     - NULL
         created_by        - SYSTEM_USER
         created_at        - default getdate()
         modified_at       - default getdate()
    */
    PRINT '  irb_submissions (from projectbodies)';
    INSERT INTO reg_website.dbo.irb_submissions (
        project, regbody, irb_number, submission_type,
        protocol_version, protocol_version_date,
        submission_date, approval_date, expiry_date, expirystatus,
        needsattentionsent, criticalsent, created_by
    )
    SELECT pb.project, pb.regbody,
           'UNKNOWN'     AS irb_number,
           'Initial'     AS submission_type,
           NULL          AS protocol_version,
           NULL          AS protocol_version_date,
           pb.submissiondate,
           NULL          AS approval_date,
           pb.expirydate,
           pb.expirystatus,
           pb.needsattentionsent,
           pb.criticalsent,
           SYSTEM_USER   AS created_by
    FROM Regulatory.dbo.projectbodies pb
    WHERE NOT EXISTS (
        SELECT 1 FROM reg_website.dbo.irb_submissions s
        WHERE s.project = pb.project AND s.regbody = pb.regbody
    );

    COMMIT;
    PRINT 'Data import completed successfully.';

END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK;
    DECLARE @msg nvarchar(4000) = ERROR_MESSAGE();
    RAISERROR('Import failed: %s', 16, 1, @msg);
    -- Do NOT proceed to Phase 4 if import failed
    RETURN;
END CATCH;


/*
===============================================================================
Phase 4: Re-add FK constraints with WITH CHECK
===============================================================================
*/
PRINT '--- Phase 4: Re-adding FK constraints ---';

-- sample_tracking FKs
ALTER TABLE sample_tracking WITH CHECK ADD CONSTRAINT FK_sample_tracking_mta_tracking
    FOREIGN KEY (project, mta_institution) REFERENCES mta_tracking (project, mta_institution);

ALTER TABLE sample_tracking WITH CHECK ADD CONSTRAINT FK_sample_tracking_sample_types
    FOREIGN KEY (sample_type) REFERENCES sample_types (sample_type);

-- mta_tracking FKs
ALTER TABLE mta_tracking WITH CHECK ADD CONSTRAINT FK_mta_tracking_mta_institutions
    FOREIGN KEY (mta_institution) REFERENCES mta_institutions (mta_institution);

ALTER TABLE mta_tracking WITH CHECK ADD CONSTRAINT FK_mta_tracking_projects
    FOREIGN KEY (project) REFERENCES projects (project);

ALTER TABLE mta_tracking WITH CHECK ADD CONSTRAINT FK_mta_tracking_regbodies
    FOREIGN KEY (regbody) REFERENCES regbodies (regbody);

-- informed_consents FKs
ALTER TABLE informed_consents WITH CHECK ADD CONSTRAINT FK_informed_consents_projects
    FOREIGN KEY (project) REFERENCES projects (project);

ALTER TABLE informed_consents WITH CHECK ADD CONSTRAINT FK_informed_consents_regbodies
    FOREIGN KEY (regbody) REFERENCES regbodies (regbody);

-- irb_submissions FKs
ALTER TABLE irb_submissions WITH CHECK ADD CONSTRAINT FK_irb_submissions_projects
    FOREIGN KEY (project) REFERENCES projects (project);

ALTER TABLE irb_submissions WITH CHECK ADD CONSTRAINT FK_irb_submissions_regbodies
    FOREIGN KEY (regbody) REFERENCES regbodies (regbody);

-- project_documents FKs
ALTER TABLE project_documents WITH CHECK ADD CONSTRAINT FK_project_documents_projects
    FOREIGN KEY (project) REFERENCES projects (project);

-- projectemails FKs
ALTER TABLE projectemails WITH CHECK ADD CONSTRAINT FK_projectemails_projects
    FOREIGN KEY (project) REFERENCES projects (project);

ALTER TABLE projectemails WITH CHECK ADD CONSTRAINT FK_projectemails_emails
    FOREIGN KEY (emailaddress) REFERENCES emails (emailaddress);

-- monitoring FKs
ALTER TABLE monitoring WITH CHECK ADD CONSTRAINT FK_monitoring_projects
    FOREIGN KEY (project) REFERENCES projects (project);

-- training FKs
ALTER TABLE training WITH CHECK ADD CONSTRAINT FK_training_projects
    FOREIGN KEY (project) REFERENCES projects (project);

-- sae FKs
ALTER TABLE sae WITH CHECK ADD CONSTRAINT [FK__sae__project__0B5CAFEA]
    FOREIGN KEY (project) REFERENCES projects (project);

PRINT 'All FK constraints re-added.';
PRINT '===============================================================================';
PRINT 'Migration complete.';
PRINT '===============================================================================';
