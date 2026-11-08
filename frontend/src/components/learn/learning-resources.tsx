import { resourcesFor } from "@/lib/learn-resources";
import { Button } from "@/components/ui/button";

export function LearningResources({ topicId, reading = true, videos = true }: {
  topicId: string; reading?: boolean; videos?: boolean;
}) {
  const resources = resourcesFor(topicId);
  if (!resources || (!reading && !videos)) return null;
  return (
    <section aria-label="Investopedia resources" className="mt-4 space-y-3">
      <p className="text-xs text-muted-foreground">Explore this topic with Investopedia</p>
      <div className="flex flex-wrap gap-3">
        {reading && <Button variant="outline" asChild>
          <a href={resources.reading.url} target="_blank" rel="noopener noreferrer" title={resources.reading.title}>
            Read: {resources.reading.title}
          </a>
        </Button>}
        {videos && <Button variant="outline" asChild>
          <a href={resources.video.url} target="_blank" rel="noopener noreferrer" title={resources.video.title}>
            Watch: {resources.video.title}
          </a>
        </Button>}
      </div>
      {videos && <p className="text-xs text-muted-foreground">Videos open on Investopedia's official YouTube channel.</p>}
    </section>
  );
}
