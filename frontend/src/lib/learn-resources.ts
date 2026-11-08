/** Curated Investopedia articles and official-channel videos, checked 2026-11-08. */
export interface LearningResource {
  title: string;
  url: string;
  publisher: "Investopedia";
}

function pair(readingTitle: string, path: string, videoTitle: string, videoId: string) {
  return {
    reading: { title: readingTitle, url: `https://www.investopedia.com/${path}`, publisher: "Investopedia" as const },
    video: { title: videoTitle, url: `https://www.youtube.com/watch?v=${videoId}`, publisher: "Investopedia" as const },
  };
}

export const LEARN_RESOURCES: Record<string, { reading: LearningResource; video: LearningResource }> = {
  personal_finance: pair("Understanding budgets", "terms/b/budget.asp", "How to build a budget", "Hnf5BRh5bdg"),
  banking: pair("Annual percentage yield", "terms/a/apy.asp", "APR vs. APY", "4hcs__p-AYA"),
  credit: pair("Understanding credit scores", "terms/c/credit_score.asp", "Three important credit score factors", "zA_Wln52w9w"),
  loan_amortization: pair("Amortization schedules", "terms/a/amortization.asp", "APR vs. APY", "4hcs__p-AYA"),
  investments: pair("Getting started with investing", "terms/i/investing.asp", "Diversification", "H41Z8oViXn0"),
  stock_markets: pair("Portfolio diversification", "terms/d/diversification.asp", "Diversification", "H41Z8oViXn0"),
  cds_iras: pair("Certificates of deposit", "terms/c/certificateofdeposit.asp", "Introduction to retirement investing", "gnK5RoHscnc"),
  mortgages: pair("How mortgages work", "terms/m/mortgage.asp", "Three important things when buying a home", "nSDZGwMN8hg"),
  interest_rate_risk: pair("Interest-rate risk", "terms/i/interestraterisk.asp", "How interest rates affect the market", "lmhkSv54YkA"),
  quant_fundamentals: pair("Time value of money", "terms/t/timevalueofmoney.asp", "Time value of money explained", "MdK-A1VQJls"),
};

export function resourcesFor(topicId: string) {
  return LEARN_RESOURCES[topicId];
}
