-- init_db.sql
CREATE USER edu_user WITH PASSWORD 'Chen030988';
CREATE DATABASE eduharness OWNER edu_user;
GRANT ALL PRIVILEGES ON DATABASE eduharness TO edu_user;