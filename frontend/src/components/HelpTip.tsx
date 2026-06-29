interface HelpTipProps {
  text: string;
  label?: string;
}

export function HelpTip({ text, label = "Más información" }: HelpTipProps) {
  return (
    <span className="help-tip" tabIndex={0} role="note" aria-label={text}>
      <span className="help-tip-trigger" aria-hidden="true" title={label}>
        ?
      </span>
      <span className="help-tip-bubble">{text}</span>
    </span>
  );
}

interface SectionIntroProps {
  title: string;
  subtitle?: string;
  help?: string;
}

export function SectionIntro({ title, subtitle, help }: SectionIntroProps) {
  return (
    <header className="section-intro">
      <div className="section-intro-text">
        <h2>{title}</h2>
        {subtitle ? <p>{subtitle}</p> : null}
      </div>
      {help ? <HelpTip text={help} label={title} /> : null}
    </header>
  );
}
