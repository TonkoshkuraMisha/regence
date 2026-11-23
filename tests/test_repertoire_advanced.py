"""Advanced starter sets (task 27.10) are created via the API in full and fit the repertoire limits."""

import pytest

from src.services import repertoire
from src.services.repertoire_starters import BY_ID

API = "/api/v1/repertoires"


@pytest.mark.parametrize("starter", ["e4_advanced", "e5_slav_advanced"])
def test_advanced_starter_is_created_whole(client, token_user_1, starter):
    response = client.post(API, headers={"Authorization": f"Bearer {token_user_1}"}, json={"starter": starter})
    assert response.status_code == 200, response.text
    rep = response.json()
    assert rep["color"] == BY_ID[starter].color
    lines = {tuple(repertoire.san_line_to_uci(line)) for line in BY_ID[starter].lines}
    plies = {line[:n] for line in lines for n in range(1, len(line) + 1)}
    # Nodes are positions: transpositions merge, so there are no more moves than distinct line starts.
    assert 300 < len(rep["moves"]) <= len(plies) <= repertoire.MAX_MOVES
