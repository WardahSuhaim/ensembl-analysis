### Bio::EnsEMBL::Analysis::RunnableDB::Finished

package Bio::EnsEMBL::Analysis::RunnableDB::Finished;

use strict;
use Bio::EnsEMBL::Utils::Exception qw(verbose throw warning);
use Bio::EnsEMBL::Pipeline::SeqFetcher::Finished_Pfetch;
use base 'Bio::EnsEMBL::Analysis::RunnableDB';

sub write_output {
	my ($self) = @_;
	my $outputs = $self->Bio::EnsEMBL::Analysis::RunnableDB::Finished::output;
    ### code db_version_searched method may be duplicated in several modules
    ### How does it get written into the input_id_analysis table?
    foreach my $runnable ( @{ $self->runnable } ) {
	    my $db_version = $runnable->get_db_version
	      if $runnable->can('get_db_version');
	    $self->db_version_searched($db_version);    # make sure we set this here
    }
    my $dbh = $self->db->dbc->db_handle;
	$dbh->begin_work;
	eval {
	    # We expect an array of arrays from output()
	    foreach my $output (@$outputs) {
	        next unless @$output;   # No feature output        
	        my $feat = $output->[0];
	        
	        # The type of adaptor used to store the data depends
	        # upon the type of the first element of @$output
	        my $adaptor = $self->get_adaptor($feat);
		    # Remove the AlignFeatures already in db from the output and 
		    # get rid of the old ones in the db (for dephtfilter features only)
		    my $all = 0;
	        if (ref($feat) =~ /AlignFeature$/) {
	            $all = 1 if($self->analysis->module eq 'DepthFilter' );
	            $self->remove_stored_AlignFeatures($adaptor, $output, $all);
	            $self->write_descriptions($output) unless ( $self->analysis->module eq 'DepthFilter' ||
	            											$self->analysis->logic_name =~ /refseq/);
	        } else {# Remove all SimpleFeatures
	        	$self->remove_all_features($adaptor);
	        }        
	        
		    my $analysis = $self->analysis;
	    	my $slice    = $self->query;
		    my $ff       = $self->feature_factory;
	        # Store features in the database
	        print STDOUT "Finished: Writting ".scalar(@$output)." ".ref($feat)." in database\n";
	        foreach my $feature (@$output) {
	        	$feature->analysis($analysis);
	        	$feature->slice($slice) if (!$feature->slice);
	        	$ff->validate($feature);
	            $adaptor->store($feature);
	        }
	    }
	    $dbh->commit;
    };
	if ($@) {
		$dbh->rollback;
		throw("UNABLE TO WRITE FEATURES IN DATABASE\n[$@]\n");
	}
}

sub output{
  my ($self, @output) = @_;
  if(!$self->{'output'}){
    $self->{'output'} = [];
  }
  if(scalar(@output)){
    push(@{$self->{'output'}}, @output);
  }
  if(ref($self->{'output'}->[0]) ne 'ARRAY')
  {
  	return [ $self->{'output'} ] ;
  }
  return $self->{'output'};
}

sub replace_output {
  my ($self, @output) = @_;
  if(scalar(@output)){
  	$self->{'output'} = [];
    push(@{$self->{'output'}}, @output);
  }
  return $self->{'output'};
}

sub remove_stored_AlignFeatures {
    my ($self, $adaptor, $output, $all) = @_;
	## create a hashtable of the contig hits stored in the database
    my $db_features =
      $adaptor->fetch_all_by_Slice($self->query, $self->analysis->logic_name);
    print STDOUT "Finished: Found ", scalar(@$db_features), " features already in db\n";
    my %db_feat = map { $self->get_feature_key($_), $_ } @$db_features;
    my %db_feat_to_del = %db_feat;
    ## remove old Uniprot features with missing sequence version. 
    if($self->analysis->logic_name eq 'Uniprot_raw') {
    	foreach my $new_f (@$output) {
    		$new_f->slice($self->query) if (!$new_f->slice);
			my $new_f_key = $self->get_feature_key($new_f,1); # get the string key without the sequence version
			my $stored_f = $db_feat{$new_f_key};
			if ($stored_f && $stored_f->display_id !~ /\.\d+/) {
				print STDOUT "Finished: Remove old Uniprot feature ".$stored_f->display_id.
							 ", replaced by ".$new_f->display_id."\n";
				$adaptor->remove($stored_f);
				delete $db_feat{$new_f_key} unless(!$db_feat{$new_f_key});
				delete $db_feat_to_del{$new_f_key} unless(!$db_feat_to_del{$new_f_key});  
        	}	    		
    		
    	}
    }
    ## remove duplicated features from output
    for (my $i = 0 ; $i < @$output ;) {
    	my $feature = $output->[$i];
        $feature->slice($self->query) if (!$feature->slice);
        my $f_key = $self->get_feature_key($feature);
        if ($db_feat{$f_key}) {
            splice(@$output, $i, 1);
			delete $db_feat_to_del{$f_key} unless(!$db_feat_to_del{$f_key}); 
        }
        else {
            $i++;
        }
    }
    ## remove the old features present in the db and not in the output 
    if($all) {
    	foreach my $f (values(%db_feat_to_del)) { $adaptor->remove($f);}
    	print STDOUT "Finished: Removed ", scalar(keys(%db_feat_to_del)), " old features from db\n";
    } 
}

sub remove_all_features {
	my ($self, $adaptor) = @_;
	my $db_features =
      $adaptor->fetch_all_by_Slice($self->query, $self->analysis->logic_name);
    foreach my $f (@$db_features) { $adaptor->remove($f);}
    print STDOUT "Finished: Removed ", scalar(@$db_features), " features through ".ref($adaptor)." \n";
}

sub write_descriptions {
    my( $self, $output ) = @_;
    my $dbobj = $self->db;
    my $seqfetcher = Bio::EnsEMBL::Pipeline::SeqFetcher::Finished_Pfetch->new;
    my %single_ids = map { $_->hseqname => 1} @$output;
    my @ids = keys(%single_ids);
    $seqfetcher->write_descriptions( $dbobj, \@ids );

}

sub get_feature_key {
	my ( $self, $feat, $uni ) = @_;
	throw(
"Must pass Bio::EnsEMBL::Analysis::RunnableDB::Finished::get_feature_key a Bio::EnsEMBL::BaseAlignFeature"
		  . "not a "
		  . $feat )
	  unless ( $feat->isa('Bio::EnsEMBL::BaseAlignFeature') );
	my $name = $feat->display_id;
	$name =~ s/\.\d// if($uni);
	return join( ':',
		$name, $feat->seq_region_name, $feat->cigar_string,
		$feat->start, $feat->end, $feat->hstart, $feat->hend );
}

sub get_adaptor {
	my ($self, $feat) = @_;

	if ( $feat->isa('Bio::EnsEMBL::DnaPepAlignFeature') ) {
		return $self->db->get_ProteinAlignFeatureAdaptor;
	}
	elsif ( $feat->isa('Bio::EnsEMBL::DnaDnaAlignFeature') ) {
		return $self->db->get_DnaAlignFeatureAdaptor;
	}
    elsif ( $feat->isa('Bio::EnsEMBL::SimpleFeature') ) {
        return $self->db->get_SimpleFeatureAdaptor;
    }
	else {
		throw('unexpected feature type: '. ref($feat));
	}
}

1;

=head1 NAME - Bio::EnsEMBL::Analysis::RunnableDB::Finished

=head1 AUTHOR

Mustapha Larbaoui B<email> ml6@sanger.ac.uk
