## Bug Report - TC_v1.2.4_001

프로그램 분석 모드에서 출력 경로에 설정 폴더가 없을 경우 진행되지 않는 경우

### Environment
version : v1.2.4

### Severity
Major

### Priority
Low

### Reproduction Steps

1. 프로그램을 실행한다
2. 적합한 분석 예정 TXT 파일 이름을 입력한다
3. 시간 형식과 분석 키워드를 입력한다
4. 분석을 진행한다

### Expected Result

- 정상적으로 분석이 진행된다

### Actual Result

- 폴더를 찾을 수 없다며 진행이 되지않고 프로그램이 종료된다

### Notes

- 채팅 수집 모드에서만 경로 폴더 생성 코드를 넣어놓으니 분석모드만 따로 진행하려고 했을 때 진행되지 않았다.
- 기존 경로 폴더 생성 코드를 모드 설정 바깥으로 빼내서 양 모드 진행 될 경우 생기도록 하였다.
- 심각성는 Major 하다고 판단했지만 채팅 분석 모드만 따로 진행하는 경우가 적다고 판단하여 priority 는 low를 주었고, 1.2.5.1 업데이트를 할때 수정하였다.

https://chatgpt.com/share/6a61b1ab-7e44-83ee-961a-e4ab23b67b20