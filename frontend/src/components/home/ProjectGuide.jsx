import React from 'react';
import { ArrowForward } from '@mui/icons-material';
import { SectionHeader, Surface } from '../ui';

const ProjectGuide = ({ cards, onOpen, title, description, actionLabel }) => (
  <section className="home-guide">
    <SectionHeader title={title} description={description} />
    <div className="home-guide__grid">
      {cards.map(({ id, icon: Icon, title: cardTitle, description: cardDescription }) => (
        <Surface
          as="button"
          type="button"
          interactive
          className="home-guide__card"
          onClick={() => onOpen(id)}
          key={id}
        >
          <span className="home-guide__icon"><Icon aria-hidden="true" /></span>
          <span className="home-guide__copy">
            <strong>{cardTitle}</strong>
            <span>{cardDescription}</span>
          </span>
          <span className="home-guide__action">
            {actionLabel}
            <ArrowForward aria-hidden="true" />
          </span>
        </Surface>
      ))}
    </div>
  </section>
);

export default ProjectGuide;
