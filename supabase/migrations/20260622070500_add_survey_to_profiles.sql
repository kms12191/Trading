-- profiles 테이블에 투자 성향 설문 조사 결과를 담기 위한 컬럼 추가
ALTER TABLE public.profiles 
ADD COLUMN invest_score INT,
ADD COLUMN invest_type TEXT,
ADD COLUMN survey_answers JSONB;
