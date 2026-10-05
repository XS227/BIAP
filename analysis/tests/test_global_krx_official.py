from global_markets.krx_official import parse_kind_company_table


def test_kind_parser_keeps_operating_company_and_pads_code():
    html = """
    <table>
      <tr><th>회사명</th><th>종목코드</th><th>업종</th><th>주요제품</th><th>상장일</th><th>결산월</th><th>대표자명</th><th>홈페이지</th><th>지역</th></tr>
      <tr><td>삼성전자</td><td>5930</td><td>전자</td><td>반도체</td><td>1975-06-11</td><td>12월</td><td>대표</td><td></td><td>경기도</td></tr>
      <tr><td>엔에이치스팩34호</td><td>123456</td><td>금융 지원 서비스업</td><td>합병</td><td>2026-09-10</td><td>12월</td><td>대표</td><td></td><td>서울</td></tr>
    </table>
    """
    rows = parse_kind_company_table(html, board="KOSPI")
    assert [row.ticker for row in rows] == ["005930"]
    assert rows[0].name == "삼성전자"
    assert rows[0].mic_code == "XKRX"
    assert rows[0].raw_provider_fields["krx_board"] == "KOSPI"
