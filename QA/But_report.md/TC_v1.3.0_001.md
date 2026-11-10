## Bug Report - TC_pre-v1.3.0_001

### Environment
version : pre-v1.3.0

### Severity
Major

### Priority
High

### Reproduction Steps

1. 프로그램을 실행한다
2. 적합한 분석 예정 TXT 파일 이름을 입력한다
3. 시간 형식과 분석 키워드를 입력한다
4. 분석을 진행한다

### Expected Result

- 각 항목별 순위가 집계된다
- 기존 설정에 따라 순위 내에서 이어지는 시간대가 병합이 된다
- 각 주제별 랭크가 순위에 따라 내림차순으로 출력된다

### Actual Result

- 기존의 최대 병합 설정을 무시하고 순위 내에서 이어지는 시간대의 병합이 계속 일어났다.
- 위 결과로 인해 기획으로 의도한 분석 결과값의 정확도가 낮아졌다.

### Notes

- 의도치 않은 버그가 발견된 코드를 발견했다.
- COPILOT이 정확한 SPEC을 사용하도록 수정하였다.
- 해당 버그를 참조해 최대 병합 갯수를 사용자가 설정할 수 있게 변동성을 가지도록 했고 이를 setting 으로 추가했다.

https://chatgpt.com/share/6a61b177-22d4-83ee-a28e-8a6a101c867d