# 실행 로그

`embedding_initial_interrupted.txt`와 `embedding_duplicate_interrupted.txt`는 인코더 중복 실행을 감지해 SIGINT로 중단한 기록이다(종료 코드 130). 첫 10,240개 텍스트 벡터의 유한성·단위 노름을 확인한 뒤 단일 인코더로 재개했으며, 이미지 인코딩은 0번째 행부터 수행했다.

최종 로그는 `embedding_final.txt`, `scales.txt`, `features.txt`, `test.txt`, `simulator.txt`, `deepfashion.txt`, `finish.txt`다. 실행 중단 기록은 품질 측정 실패나 완료된 최종 학습 결과와 구분한다. CPU 작업을 병행했으므로 경과 시간을 격리된 서빙 지연으로 해석하지 않는다.
