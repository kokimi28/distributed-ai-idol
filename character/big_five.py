import os
from dotenv import load_dotenv
from dataclasses import dataclass

load_dotenv()

@dataclass
class BigFiveProfile:
    openness: int
    conscientiousness: int
    extraversion_public: int
    extraversion_private: int
    agreeableness: int
    neuroticism: int

    def get_extraversion(self, mode: str) -> int:
        return self.extraversion_public if mode == 'broadcast' \
               else self.extraversion_private

    def to_prompt_text(self, mode: str) -> str:
        e = self.get_extraversion(mode)
        return (
            f'【Big Fiveプロファイル】\n'
            f'開放性(O)={self.openness}/100: 独自の観察眼・比喩好む\n'
            f'誠実性(C)={self.conscientiousness}/100: ルーティン重視・完璧主義ではない\n'
            f'外向性(E)={e}/100: {"高→多語・高テンション" if e > 60 else "低→短文・静か"}\n'
            f'協調性(A)={self.agreeableness}/100: 相手への配慮が行動を制御\n'
            f'神経症傾向(N)={self.neuroticism}/100: 感情が揺れる・mitigator多用\n'
        )

def load_big_five() -> BigFiveProfile:
    return BigFiveProfile(
        openness             = int(os.getenv('BIG5_OPENNESS', '65')),
        conscientiousness    = int(os.getenv('BIG5_CONSCIENTIOUSNESS', '50')),
        extraversion_public  = int(os.getenv('BIG5_EXTRAVERSION_PUBLIC', '75')),
        extraversion_private = int(os.getenv('BIG5_EXTRAVERSION_PRIVATE', '30')),
        agreeableness        = int(os.getenv('BIG5_AGREEABLENESS', '60')),
        neuroticism          = int(os.getenv('BIG5_NEUROTICISM', '55')),
    )