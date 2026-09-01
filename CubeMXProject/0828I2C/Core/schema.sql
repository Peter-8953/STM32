--
-- PostgreSQL database dump
--
-- 2026-08-23 更新：readings 新增 seq 欄位，command_logs / time_readings 的
-- seq 欄位順序往前移，三張「單次操作」表統一成
--   id, device_id, seq, <本表資料值欄位...>, recorded_at
-- 對應 db/models.py 的 CREATE_READINGS / CREATE_COMMAND_LOGS /
-- CREATE_TIME_READINGS 與新增的 rebuild migration。
--

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: command_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.command_logs (
    id bigint NOT NULL,
    device_id smallint,
    seq integer,
    command character varying(32) NOT NULL,
    status character varying(8),
    recorded_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.command_logs OWNER TO postgres;

--
-- Name: command_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.command_logs_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.command_logs_id_seq OWNER TO postgres;

--
-- Name: command_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.command_logs_id_seq OWNED BY public.command_logs.id;


--
-- Name: devices; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.devices (
    id smallint NOT NULL,
    name character varying(64),
    port character varying(32),
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.devices OWNER TO postgres;

--
-- Name: readings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.readings (
    id bigint NOT NULL,
    device_id smallint,
    seq integer,
    read_at timestamp with time zone NOT NULL,
    temperature numeric(5,2) NOT NULL,
    recorded_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.readings OWNER TO postgres;

--
-- Name: readings_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.readings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.readings_id_seq OWNER TO postgres;

--
-- Name: readings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.readings_id_seq OWNED BY public.readings.id;


--
-- Name: time_readings; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.time_readings (
    id bigint NOT NULL,
    device_id smallint,
    seq integer,
    device_time timestamp with time zone NOT NULL,
    recorded_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.time_readings OWNER TO postgres;

--
-- Name: time_readings_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.time_readings_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.time_readings_id_seq OWNER TO postgres;

--
-- Name: time_readings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.time_readings_id_seq OWNED BY public.time_readings.id;


--
-- Name: command_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.command_logs ALTER COLUMN id SET DEFAULT nextval('public.command_logs_id_seq'::regclass);


--
-- Name: readings id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.readings ALTER COLUMN id SET DEFAULT nextval('public.readings_id_seq'::regclass);


--
-- Name: time_readings id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.time_readings ALTER COLUMN id SET DEFAULT nextval('public.time_readings_id_seq'::regclass);


--
-- Name: command_logs command_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.command_logs
    ADD CONSTRAINT command_logs_pkey PRIMARY KEY (id);


--
-- Name: devices devices_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.devices
    ADD CONSTRAINT devices_pkey PRIMARY KEY (id);


--
-- Name: readings readings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.readings
    ADD CONSTRAINT readings_pkey PRIMARY KEY (id);


--
-- Name: time_readings time_readings_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.time_readings
    ADD CONSTRAINT time_readings_pkey PRIMARY KEY (id);


--
-- Name: command_logs command_logs_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.command_logs
    ADD CONSTRAINT command_logs_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id);


--
-- Name: readings readings_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.readings
    ADD CONSTRAINT readings_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id);


--
-- Name: time_readings time_readings_device_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.time_readings
    ADD CONSTRAINT time_readings_device_id_fkey FOREIGN KEY (device_id) REFERENCES public.devices(id);


--
-- PostgreSQL database dump complete
--