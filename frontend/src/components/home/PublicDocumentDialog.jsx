import React from 'react';
import {
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
} from '@mui/material';
import { Close } from '@mui/icons-material';
import './PublicDocumentDialog.css';

const PublicDocumentDialog = ({
  documentId,
  language,
  getDocument,
  onClose,
  closeLabel,
}) => {
  const document = documentId ? getDocument(language, documentId) : null;

  return (
    <Dialog
      open={Boolean(document)}
      onClose={onClose}
      fullWidth
      maxWidth="md"
      scroll="paper"
      className="home-document-dialog"
    >
      {document && (
        <>
          <DialogTitle component="div" className="home-document-dialog__titlebar">
            <h2>{document.title}</h2>
            <IconButton
              aria-label={closeLabel}
              onClick={onClose}
              className="home-document-dialog__close"
            >
              <Close />
            </IconButton>
          </DialogTitle>
          <DialogContent dividers className="home-document-dialog__content">
            <p className="home-document-dialog__intro">{document.intro}</p>
            <div className="home-document-dialog__sections">
              {document.sections.map((section) => (
                <section key={section.title}>
                  <h3>{section.title}</h3>
                  <p>{section.body}</p>
                </section>
              ))}
            </div>
          </DialogContent>
        </>
      )}
    </Dialog>
  );
};

export default PublicDocumentDialog;
