import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LearningResources } from "@/components/learn/learning-resources";
import { LEARN_RESOURCES } from "@/lib/learn-resources";

afterEach(cleanup);

describe("Investopedia learning resources", () => {
  it("links each curriculum topic to a direct article and an actual video", () => {
    expect(Object.keys(LEARN_RESOURCES)).toHaveLength(10);
    for (const resources of Object.values(LEARN_RESOURCES)) {
      expect(new URL(resources.reading.url).hostname).toBe("www.investopedia.com");
      const video = new URL(resources.video.url);
      expect(video.hostname).toBe("www.youtube.com");
      expect(video.pathname).toBe("/watch");
      expect(video.searchParams.get("v")).toMatch(/^[a-zA-Z0-9_-]{11}$/);
    }
  });

  it("renders real links and respects the reading/video switches", () => {
    const { rerender } = render(<LearningResources topicId="personal_finance" />);
    expect(screen.getByRole("link", { name: /Read:/ })).toHaveAttribute("href", "https://www.investopedia.com/terms/b/budget.asp");
    expect(screen.getByRole("link", { name: /Watch:/ })).toHaveAttribute("href", "https://www.youtube.com/watch?v=Hnf5BRh5bdg");
    rerender(<LearningResources topicId="personal_finance" reading={false} />);
    expect(screen.queryByRole("link", { name: /Read:/ })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Watch:/ })).toBeInTheDocument();
  });
});
